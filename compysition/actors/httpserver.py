#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
#  wsgi.py
#
#  Copyright 2014 James Hulett <james.hulett@cuanswers.com>
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.

from collections import defaultdict
from datetime import datetime
import json
import mimeparse
import re

from bottle import BaseRequest, Bottle, HTTPError, HTTPResponse, request
from gevent import pywsgi
from gevent.queue import Queue

from compysition.actor import Actor
from compysition.errors import InvalidEventDataModification, MalformedEventData, ResourceNotFound
from compysition.event import HttpEvent, JSONHttpEvent, XMLHttpEvent

from compysition.util import ignore

BaseRequest.MEMFILE_MAX = 1024 * 1024 # (or whatever you want)

class ContentTypePlugin(object):
    """**Bottle plugin that filters basic content types that are processable by Compysition**"""

    DEFAULT_VALID_TYPES = ("text/xml",
                           "application/xml",
                           "text/plain",
                           "text/html",
                           "application/json",
                           "application/x-www-form-urlencoded")
    '''
    # with the change to the apply function the DEFAULT_VALID_TYPES should be as follows to match content-type/event mapping
    DEFAULT_VALID_TYPES = ("text/xml",
                           "application/xml",
                           "text/plain",
                           "text/html",
                           "application/json",
                           "application/x-www-form-urlencoded",
                           "application/json+schema",
                           "application/xml+schema")
    '''
    name = "ctypes"
    api = 2

    def __init__(self, default_types=None):
        self.default_types = default_types or self.DEFAULT_VALID_TYPES

    def apply(self, callback, route):
        #ATTENTION
        #Bottle expects a decorator
        #This should be implemented as below
        ctype = request.content_type.split(';')[0]
        ignore_ctype = route.config.get('ignore_ctype', False) or request.content_length < 1
        if ignore_ctype or ctype in route.config.get('ctypes', self.default_types):
            return callback
        else:
            raise HTTPError(415, "Unsupported Content-Type '{_type}'".format(_type=ctype))

    '''
    def apply(self, callback, route):
        def callback_wrapper(*args, **kwargs):
            ctype = request.content_type.split(';')[0]
            ignore_ctype = route.config.get('ignore_ctype', False) or request.content_length < 1
            if ignore_ctype or ctype in route.config.get('ctypes', self.default_types):
                return callback(*args, **kwargs)
            else:
                raise HTTPError(415, "Unsupported Content-Type '{_type}'".format(_type=ctype))
        return callback_wrapper
    '''

class HTTPServer(Actor, Bottle):
    """**Receive events over HTTP.**

    Actor runs a pywsgi gevent webserver, using an optional routes json file for complex routing using Bottle

    Parameters:
        name (str):
            | The instance name.
        address(Optional[str]):
            | The address to bind to.
            | Default: 0.0.0.0
        port(Optional[int]):
            | The port to bind to.
            | Default: 8080
        keyfile(Optional([str]):
            | In case of SSL the location of the keyfile to use.
            | Default: None
        certfile(Optional[str]):
            | In case of SSL the location of the certfile to use.
            | Default: None
        routes_config(Optional[dict]):
            | This is a JSON object that contains a list of Bottle route config kwargs
            | Default: {"routes": [{"path: "/<queue>", "method": ["POST"]}]}
            | Field values correspond to values used in bottle.Route class
            | Special values:
            |    id(Optional[str]): Used to identify this route in the json object
            |    base_path(Optional[str]): Used to identify a route that this route extends, using the referenced id

    Examples:
        Default:
            http://localhost:8080/foo is mapped to 'foo' queue
            http://localhost:8080/bar is mapped to 'bar' queue
        routes_config:
            routes_config {"routes": [{"path: "/my/url/<queue>", "method": ["POST"]}]}
                http://localhost:8080/my/url/goodtimes is mapped to 'goodtimes' queue


    """

    DEFAULT_ROUTE = {
        "routes":
            [
                {
                    "id": "base",
                    "path": "/<queue>",
                    "method": [
                        "POST"
                    ]
                }
            ]
    }

    input = HttpEvent
    output = HttpEvent

    QUEUE_REGEX = re.compile("<queue:re:[a-zA-Z_0-9]+?>")

    # Order matters, as this is used to resolve the returned content type preserved in the accept header, in order of increasing preference.
    _TYPES_MAP = [('application/xml+schema', XMLHttpEvent),
                  ('application/json+schema', JSONHttpEvent),
                  ('*/*', HttpEvent),
                  ('text/plain', HttpEvent),
                  ('text/html', XMLHttpEvent),
                  ('text/xml', XMLHttpEvent),
                  ('application/xml', XMLHttpEvent),
                  ('application/json', JSONHttpEvent)]
    CONTENT_TYPES = [_type[0] for _type in _TYPES_MAP]
    CONTENT_TYPE_MAP = defaultdict(lambda: JSONHttpEvent,
                                   _TYPES_MAP)

    X_WWW_FORM_URLENCODED_KEY_MAP = defaultdict(lambda: HttpEvent, {"XML": XMLHttpEvent, "JSON": JSONHttpEvent})
    X_WWW_FORM_URLENCODED = "application/x-www-form-urlencoded"

    WSGI_SERVER_CLASS = pywsgi.WSGIServer

    def combine_base_paths(self, route, named_routes):
        base_path_id = route.get('base_path', None)
        if base_path_id:
            base_path = named_routes.get(base_path_id, None)
            if base_path:
                return HTTPServer._normalize_queue_definition(self.combine_base_paths(base_path, named_routes) + route['path'])
            else:
                raise KeyError("Base path '{base_path}' doesn't reference a defined path ID".format(base_path=base_path_id))
        else:
            return route.get('path')


    @staticmethod
    def _parse_queue_variables(path):
        return HTTPServer.QUEUE_REGEX.findall(path)

    @staticmethod
    def _parse_queue_names(path):
        path_variables = HTTPServer._parse_queue_variables(path)
        return [s.replace("<queue:re:", '')[:-1] for s in path_variables]

    @staticmethod
    def _normalize_queue_definition(path):
        """
        This method is used to filter the queue variable in a path, to support the idea of base paths with multiple queue
        definitions. In effect, the <queue> variable in a path is provided at the HIGHEST level of definition. AKA: A higher
        level route containing a <queue:re:foo> will override the definition of <queue:re:bar> in a base_path.

        e.g. /<queue:re:foo>/<queue:re:bar> -> /foo/<queue:re:bar>

        This ONLY works for SIMPLE regex cases, which should be the case anyway for the queue name.
        """

        path_variables = HTTPServer._parse_queue_variables(path)
        path_names = HTTPServer._parse_queue_names(path)

        for path_variable in path_variables[:-1]:
            path = path.replace(path_variable, path_names.pop(0))

        return path

    def __init__(self, name, address="0.0.0.0", port=8080, keyfile=None, certfile=None, routes_config=None, send_errors=False, use_response_wrapper=True, process_bottle_exceptions=False, *args, **kwargs):
        Actor.__init__(self, name, *args, **kwargs)
        Bottle.__init__(self)
        self.blockdiag_config["shape"] = "cloud"
        self.address = address
        self.port = port
        self.keyfile = keyfile
        self.certfile = certfile
        self.responders = {}
        self.send_errors = send_errors
        self.use_response_wrapper = use_response_wrapper
        routes_config = routes_config or self.DEFAULT_ROUTE

        if isinstance(routes_config, str):
            routes_config = json.loads(routes_config)

        if isinstance(routes_config, dict):
            named_routes = {route['id']:{'path': route['path'], 'base_path': route.get('base_path', None)} for route in routes_config.get('routes') if route.get('id', None)}
            for route in routes_config.get('routes'):
                callback = getattr(self, route.get('callback', 'callback'))
                if route.get('base_path', None):
                    route['path'] = self.combine_base_paths(route, named_routes)

                if not route.get('method', None):
                    route['method'] = []

                self.logger.debug("Configured route '{path}' with methods '{methods}'".format(path=route['path'], methods=route['method']))
                self.route(callback=callback, **route)

        self.wsgi_app = self
        self.wsgi_app.install(ContentTypePlugin())
        if process_bottle_exceptions:
            self.default_error_handler = self.__default_error_handler

    def __call__(self, e, h):
        """**Override Bottle.__call__ to strip trailing slash from incoming requests**"""

        e['PATH_INFO'] = e['PATH_INFO'].rstrip('/')
        return Bottle.__call__(self, e, h)

    def __default_error_handler(self, res):
        '''
            Handles Bottle raised exceptions and applies event based error messaging and response formatting
        '''
        event = HttpEvent(
            environment=self._format_bottle_env(request.environ), 
            _error=MalformedEventData(res.body), 
            accept=self._get_accept(), 
            status=res._status_line)
        event = self._process_response_accept(event=event)
        local_response = self._create_response(event=event)
        res.body = local_response.body
        res.headers.update(**local_response.headers)
        return res.body # we want to still use bottle built attributes s.a. status
        
    def _format_json_response_data(self, event):
        response_dict = event.data
        if self.use_response_wrapper and getattr(event, "use_response_wrapper", True):
            response_dict = {'data': event.data}

        if event.pagination is not None:
            limit, offset = event._pagination['limit'], event._pagination['offset']
            qs = '?limit={limit}&offset={offset}'
            base_url = '{path}'.format(path=event.environment['PATH_INFO'])

            links = {'prev': "{}{}".format(base_url, qs.format(limit=limit, offset=offset))}

            if limit <= len(event.data):
                links['next'] = base_url + qs.format(limit=limit, offset=offset + limit)

            response_dict.update({'_pagination': links})

        return json.dumps(response_dict)

    def _format_response_data(self, event):
        """
        Meant to return a json response nested under a data tag if it isn't already done so, or return formatted
        errors under the "errors" tag. If _pagination attribute exists on the event, will attempt to generate pagination
        links based on limit and offset. Pagination is currently only supported for JSON responses.
        """
        if event.error:
            if isinstance(event, JSONHttpEvent):
                return json.dumps({"errors": event.format_error()})
            return event.error_string()
        #ATTENTION
        # So pagination gets skipped if data wrapper already exists?
        if not isinstance(event.data, (list, dict, str)) or \
                (isinstance(event.data, dict) and len(event.data) == 1 and event.data.get("data", None)):
            # This seems to be an implicit check for whether or not the data is an XMLEvent
            return event.data_string()
        return self._format_json_response_data(event=event)

    def _create_response(self, event):
        local_response = HTTPResponse(headers=event.headers)
        status, status_message = event.status
        local_response.status = "{code} {message}".format(code=status, message=status_message)
        local_response.set_header("Content-Type", event.content_type)
        local_response.body = "" if int(status) == 204 else self._format_response_data(event)
        return local_response

    def _process_response_accept(self, event, original_event_class=HttpEvent):
        # accept defaults to */* so previously never changed from internal event type unless accept was defined in request
        # now if accept is set to */* then defaults to the incoming request content-type
        _default_accept = "*/*"
        accept = event.get('accept', _default_accept)
        accept = original_event_class.content_type if accept == _default_accept else accept 

        if not isinstance(event, self.CONTENT_TYPE_MAP[accept]):
            self.logger.warning(
                "Incoming event did did not match the clients Accept format. Converting '{current}' to '{new}'".format(
                    current=type(event), new=original_event_class.__name__))
            #ATTENTION
            #Is it even possible to respond with a 'text/plain' Content-Type?
            #I'm not sure we do enough to respond with acceptable types.
            #Maybe we could look into hard vs soft conversions
            return event.convert(self.CONTENT_TYPE_MAP[accept])
        return event  

    def consume(self, event, *args, **kwargs):
        # There is an error that results in responding with an empty list that will cause an internal server error
        original_event_class, response_queue = self.responders.pop(event.event_id, None)

        if response_queue is not None:
            event = self._process_response_accept(event=event, original_event_class=original_event_class)
            local_response = self._create_response(event=event)
            response_queue.put(local_response)
            response_queue.put(StopIteration)
            self.logger.info("[{status}] Service '{service}' Returned in {time:0.0f} ms".format(
                    service=event.service,
                    status=local_response.status,
                    time=(datetime.now()-event.created).total_seconds() * 1000),
                event=event)
        else:
            self.logger.warning("Received event response for an unknown event ID. The request might have already received a response", event=event)

    def _format_bottle_env(self, environ):
        """**Filters incoming bottle environment of non-serializable objects, and adds useful shortcuts**"""
        query_string_data = {key: value for key, value in environ["bottle.request"].query.iteritems()}
        environ = {key: value for key, value in environ.iteritems() if isinstance(value, (str, tuple, bool, dict))}
        environ['QUERY_STRING_DATA'] = query_string_data
        return environ

    def _get_accept(self):
        accept_header = request.headers.get("Accept", "*/*")
        with ignore(ValueError):
            return mimeparse.best_match(self.CONTENT_TYPES, accept_header)
        self.logger.warning("Invalid mimetype defined in client Accepts header. '{accept}' is not a valid mime type".format(accept=accept_header))
        return "*/*"

    def _interpret_ctype(self, ctype):
        if ctype == self.X_WWW_FORM_URLENCODED:
            if len(request.forms) < 1:
                raise MalformedEventData("Mismatched content type")
            else:
                key, value = next(request.forms.iteritems())
                event_class, data = self.X_WWW_FORM_URLENCODED_KEY_MAP[key], value
        else:
            event_class = self.CONTENT_TYPE_MAP[ctype]
            with ignore(ValueError):
                data = request.body.read()
        if data != '':
            return event_class, data
        return event_class, None

    def callback(self, queue=None, *args, **kwargs):
        queue_name = queue or self.name
        queue = self.pool.outbound.get(queue_name, None)

        #I think we should try to grab the first valid ctype before defaulting to first vs only using the first
        ctype = request.content_type.split(';')[0]
        ctype = None if ctype == '' else ctype

        accept = self._get_accept()

        try:
            event_class, data = None, None
            environment = self._format_bottle_env(request.environ)

            if queue is None:
                self.logger.error("Received {method} request with URL '{url}'. Queue name '{queue_name}' was not found".format(
                    method=request.method,
                    url=request.path,
                    queue_name=queue_name))
                raise ResourceNotFound("Service '{0}' not found".format(queue_name))

            event_class, data = self._interpret_ctype(ctype=ctype)

            event = event_class(environment=environment, service=queue_name, data=data, accept=accept, **kwargs)
        except (ResourceNotFound, InvalidEventDataModification, MalformedEventData) as err:
            event_class = event_class or JSONHttpEvent
            event = event_class(environment=environment, service=queue_name, accept=accept, **kwargs)
            event.error = err
            if not self.send_errors:
                queue = self.pool.inbound[next(self.pool.inbound.iterkeys())]

        self.logger.info('[{address}] {method} {url}'.format(address=request.remote_addr,
                                                             method=request.method,
                                                             url=request.url), event=event)
        response_queue = Queue()
        self.responders.update({event.event_id: (event_class, response_queue)})
        local_response = response_queue
        self.logger.info("Received {0} request for service {1}".format(request.method, queue_name), event=event)
        self.send_event(event, queues=[queue])

        return local_response

    def post_hook(self):
        self.__server.close()
        self.__server.stop()
        self.__server.socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.logger.info("Stopped serving")

    def __serve(self):
        if self.keyfile is not None and self.certfile is not None:
            self.__server = self.WSGI_SERVER_CLASS((self.address, self.port), self, keyfile=self.keyfile, certfile=self.certfile)
        else:
            self.__server = self.WSGI_SERVER_CLASS((self.address, self.port), self, log=None)
        self.logger.info("Serving on {address}:{port}".format(address=self.address, port=self.port))
        self.__server.start()

    def pre_hook(self):
        self.__serve()