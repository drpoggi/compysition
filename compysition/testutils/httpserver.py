import gevent
from contextlib import contextmanager

from compysition.actors.httpserver import HTTPServer
from compysition.util import PY2, ignore, itervalues, get_uuid, try_decode

__all__ = ["MockTimeoutException", "send_mock_request", "create_test_server", "get_mock_response"]

#base environ that simulates typical wsgi generated environ
_BASE_MOCK_ENVIRON = {
        'GATEWAY_INTERFACE': 'CGI/1.1',
        'SCRIPT_NAME': '',
        'wsgi.version': (1, 0),
        'wsgi.multithread': False, 
        'wsgi.multiprocess': False, 
        'wsgi.run_once': False, 
        'SERVER_PROTOCOL': 'HTTP/1.1', 
        'HTTP_ACCEPT_ENCODING': 'gzip, deflate', 
        'HTTP_ACCEPT': '*/*', 
        'HTTP_CONNECTION': 'keep-alive', 
        'wsgi.input_terminated': True
    }

#headers that don't utilize pywsgi's 'HTTP_' prefix
_SPECIAL_HEADERS = ["CONTENT_TYPE", "CONTENT_LENGTH"]

#default mock request timeout
_DEFAULT_TIMEOUT = 0.5

#maps event_id to processor wrapper in order to respond to timed-out requests
_event_wrapper_map = {}
_wrapper_event_map = {}

#maps wrapper to wrapper's greenlet
_wrapper_greenlet_map = {}

class _MockServer(gevent.pywsgi.WSGIServer):
    '''Non-socket HTTP server'''

    def __init__(self, server_address, RequestHandlerClass, *args, **kwargs):
        gevent.baseserver.BaseServer.__init__(self, server_address, RequestHandlerClass)

    def server_bind(self):
        pass

    def init_socket(self):
        pass

class _MockHandler(gevent.pywsgi.WSGIHandler):
    '''Non-socket HTTP handler'''

    def setup(self):
        self.connection = self.request
        self.rfile, self.wfile = self.connection

    def finish(self):
        pass

class _MockInput:
    '''Mock object used to simulate gevent Input object'''

    def __init__(self, data):
        self.data = data

    def read(self, size, *args, **kwargs):
        resp = "".join(self.data[:size])
        self.data = "".join(self.data[len(resp):])
        return resp if PY2 else resp.encode()

def _parse_url(url):
    '''seperates url into parts'''
    if url.startswith("http"):
        schema, url = url.split(":", 1)
        url = url[2:]
    else:
        schema = "http"
    domain, path = url.split("/", 1)
    path = "/{}".format(path)
    domains = domain.split(":", 1)
    if len(domains) > 0:
        domain, port = domains[0], int(domains[1])
    else:
        port = 80
    paths = path.split('?', 1)
    path, query = paths if len(paths) > 1 else (paths[0], "")
    return schema, domain, port, path, query

def _random_port():
    '''generates random number in range of valid ports'''
    from random import randint
    return randint(1,65535)

class _MockIO:
    '''Mock object used to simulate gevent io object'''

    def __init__(self):
        self.data = ""

    def write(self, data):
        self.data = data

def _assemble_environ(method, url, data, headers):
    #interpret request
    headers = {header.upper().replace('-','_'): value for header, value in headers.items()}
    method = method.upper()
    schema, domain, port, path, query = _parse_url(url=url)

    #build environment
    environ = dict(_BASE_MOCK_ENVIRON)
    environ['wsgi.url_scheme'] = schema
    environ['wsgi.errors'] = _MockIO()
    environ['REQUEST_METHOD'] = method
    environ['PATH_INFO'] = path
    environ['QUERY_STRING'] = query
    environ['SERVER_NAME'] = domain
    environ['SERVER_PORT'] = str(port)
    environ['REMOTE_ADDR'], environ['REMOTE_PORT'] = headers.get("HOST", "{}:{}".format("127.0.0.1",str(_random_port()))).split(":")
    for header, value in headers.items():
        if header in _SPECIAL_HEADERS:
            environ[header] = value
        else:
            new_header = "HTTP_{}".format(header)
            environ[new_header] = value
    if method != "GET":
        environ['CONTENT_LENGTH'] = environ.get('CONTENT_LENGTH', len(str(data)))
    if environ.get('CONTENT_LENGTH', None) is not None:
        environ['wsgi.input'] = _MockInput(data=data)
    return environ

class _RequestProcessingWrapper:
    '''Mock object used to collect various request attributes'''
    def __init__(self):
        self.id = get_uuid()

    def __start_response(self, status_line, header_list, *args, **kwargs):
        self.status_line = status_line
        self.status = int(self.status_line.split(' ', 1)[0])
        self.headers = {header_item[0]: header_item[1] for header_item in header_list}

    def __call__(self, app, environ, event):
        app._request_processing_wrapper = self
        self.body = app(environ, self.__start_response)
        self.body = try_decode(self.body[0])
        event.set()
        return self.headers, self.body, self.status, self.status_line

class MockTimeoutException(Exception): pass

def _process_timeout(greenlet, event, timeout):
    if timeout < 0:
        event.wait()
    else:
        if not event.wait(timeout):
            raise MockTimeoutException
    gevent.joinall([greenlet])

def _clean(wrapper_id):
    global _wrapper_greenlet_map, _event_wrapper_map, _wrapper_event_map
    with ignore(KeyError):
        del _wrapper_greenlet_map[wrapper_id]
    with ignore(KeyError):
        event_id = _wrapper_event_map[wrapper_id]
        del _event_wrapper_map[event_id]
    with ignore(KeyError):
        del _wrapper_event_map[wrapper_id]

def send_mock_request(httpserver_actor, method, url, data="", headers={}, timeout=_DEFAULT_TIMEOUT):
    '''entry point for simulating HTTPServer request handling'''
    global _wrapper_greenlet_map

    #format request
    environ = _assemble_environ(method=method, url=url, data=data, headers=headers)
    timeout = -1 if timeout is None or timeout <= 0 else timeout
    
    #process request with timeout funcionality
    event = gevent.event.Event()
    event.clear()
    _wrapper = _RequestProcessingWrapper()
    g = gevent.spawn(_wrapper, app=httpserver_actor, environ=environ, event=event)
    _wrapper_greenlet_map[_wrapper.id] = (g, event)
    _process_timeout(greenlet=g, event=event, timeout=timeout)
    _clean(wrapper_id=_wrapper.id)
    return g.value

def get_mock_response(httpserver_actor, event, timeout=_DEFAULT_TIMEOUT):
    '''entry point for simulating HTTPServer response handling'''
    global _wrapper_greenlet_map, _event_wrapper_map

    #format
    timeout = -1 if timeout is None or timeout <= 0 else timeout

    #put event on an inbound queue
    next(itervalues(httpserver_actor.pool.inbound)).put(event)

    #get original request info
    wrapper_id = _event_wrapper_map[event.event_id].id
    g, event = _wrapper_greenlet_map[wrapper_id]

    #process response
    _process_timeout(greenlet=g, event=event, timeout=timeout)
    _clean(wrapper_id=wrapper_id)
    return g.value

def create_test_server(func=None, 
        server_class=HTTPServer, 
        name="http_server", 
        address='0.0.0.0', 
        port=_random_port(), 
        routes_config={"routes":[{"id": "base","path": "/<queue:re:[a-zA-Z_0-9]+?>", "method": ["POST"]}]},
        outbound_queues=[],
        inbound_queues=['error'],
        start=True,
        *server_args, **server_kwargs):
    '''decorator factory used to define HTTPServer parms'''

    from compysition.queue import Queue as CQueue

    class MockHTTPServer(server_class):
        '''
            Dynamic Non-socket Compysition HTTPServer
            -- Intended for use on HTTPServer or subclass of HTTPServer
        '''

        WSGI_SERVER_CLASS = _MockServer

        def _handle(self, *args, **kwargs):
            '''Ties event_id to the calling request wrapper'''
            global _event_wrapper_map, _wrapper_event_map

            #pre handle
            pre_ids = [key for key in self.responders.keys()]
            _wrapper = self._request_processing_wrapper
            del self._request_processing_wrapper

            #handle
            result = server_class._handle(self, *args, **kwargs)

            try:
                #get event_id
                new_event_id = [key for key in self.responders.keys() if key not in pre_ids][0]
            except (AttributeError, IndexError):
                pass
            else:
                #map event_id to wrapper
                _event_wrapper_map[new_event_id] = _wrapper
                _wrapper_event_map[_wrapper.id] = new_event_id
            return result

    def decorator(func):
        '''default test decorator'''

        class _empty:
            def __enter__(self, *args, **kwargs): return self
            def __exit__(self, *args, **kwargs): pass
            
        def _try_parms(func, self, *args, **kwargs):
            '''
                func used to try and pass base request info to decorated method
                essentially making these base dicts optional
            '''
            _base_request_kwargs = {
                "httpserver_actor": self.server_actor,
                "method": "POST",
                "url": "http://localhost:34567/sample_service",
                "timeout": 0.05
            }
            _base_resp_kwargs = {
                "httpserver_actor": self.server_actor,
                "timeout": 0.05
            }
            parms = (_base_request_kwargs, _base_resp_kwargs)
            for i in range(len(parms), 0, -1):
                with ignore(TypeError):
                    return func(self, *(args+parms[:i]), **kwargs)
            return func(self, *args, **kwargs)

        def wrapper(self, *args, **kwargs):
            '''test wrapper/server setup'''
            #create server
            self.server_actor = MockHTTPServer(name,
                address=address, 
                port=port, 
                routes_config=routes_config,
                *server_args, **server_kwargs)

            #attach/create queues
            for queue_name in outbound_queues:
                self.server_actor.pool.outbound.add(queue_name)
            for queue_name in inbound_queues:
                queue = self.server_actor.pool.outbound[queue_name] if queue_name in outbound_queues else CQueue(queue_name)
                self.server_actor.register_consumer(queue_name, queue)

            #execute
            error_handler, context = (self.server_actor.stop, self.server_actor) if start else ((lambda:None), _empty())
            with context:
                try:
                    _try_parms(func, self, *args, **kwargs)
                except AssertionError as e:
                    error_handler()
                    raise

            #teardown
            global _event_wrapper_map, _wrapper_event_map, _wrapper_greenlet_map
            _event_wrapper_map, _wrapper_event_map, _wrapper_greenlet_map = {}, {}, {}
            del self.server_actor
        return wrapper

    #determines whether decorator factory is being used as factory or decorator
    return decorator if func is None else decorator(func)


