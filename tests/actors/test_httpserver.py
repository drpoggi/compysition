import json
from lxml import etree
import unittest
from contextlib import contextmanager

from compysition.actors.httpserver import HTTPServer
from compysition.event import JSONHttpEvent, HttpEvent, XMLHttpEvent
from compysition.testutils.test_actor import TestActorWrapper
from compysition.queue import Queue
import requests
from compysition.errors import ResourceNotFound, InvalidEventDataModification

import socket
from contextlib import closing
from gevent import sleep
import pytest
from gevent.pywsgi import WSGIHandler, WSGIServer
import mimetools
from StringIO import StringIO

class HTTPServerTestWrapper:

    class MockHandler(WSGIHandler):

        def __init__(self, sock=None, address=None, server=None, *args, **kwargs):
            self.wrapper = server.wrapper
            self.wrapper._handler = self
            super(HTTPServerTestWrapper.MockHandler, self).__init__(sock, address, server, rfile=StringIO(""), *args, **kwargs)
            self.header_data = None
            self.status = None
            self.status_line = None

        def read_requestline(self):
            return "%s %s HTTP/1.1" % (self.mocked_method.upper(), self.mocked_path)
            
        def __break_message(self, message, split="\n"):
            lines = str(message).split(split)
            oh = {}
            for line in lines:
                header, value = line.split(":", 1)
                header, value = header.strip(), value.strip()
                oh[header] = value
            return oh

        def __build_message(self, json):
            message_lines = []
            for header, value in json.iteritems():
                message_lines.append("%s: %s" % (header, value))
            return mimetools.Message(StringIO("\n".join(message_lines)))

        def __get_case_insensitive_header(self, target_header):
            for header, value in self.mocked_headers.iteritems():
                if header.lower() == target_header.lower():
                    return value
            return None

        def read_request(self, raw_requestline, *args, **kwargs):
            self.command, self.path, self.request_version = raw_requestline.split()
            self.close_connection = False
            self.content_length = self.__get_case_insensitive_header(target_header="Content-Length")
            self.headers = self.__build_message(json=self.mocked_headers)
            return True

        def get_environ(self):
            old_rfile = self.rfile
            self.rfile = StringIO(self.mocked_content)
            env = super(HTTPServerTestWrapper.MockHandler, self).get_environ()
            self.rfile = old_rfile
            return env

        def __pop_first_line(self, data, split="\n"):
            lines = data.split(split)
            lines = [line for line in lines if len(line.strip()) > 0]
            return lines[0], split.join(lines[1:])

        def _sendall(self, *args, **kwargs):
            data = str(args[0])
            if self.header_data is None:
                line, data = self.__pop_first_line(data=data, split="\r\n")
                self.status_line = line.split(" ", 1)[1]
                self.status = int(self.status_line.split()[0])
                self.header_data = self.__break_message(message=data, split="\r\n")
            else:
                self.wrapper.responses.append((self.header_data, data, self.status, self.status_line))
                self.header_data, self.status, self.status_line = None, None, None
            
    class MockWSGIServer(WSGIServer):
        def __init__(self, socket, application, *args, **kwargs):
            self.wrapper = application.wrapper
            self.wrapper._server = self
            super(HTTPServerTestWrapper.MockWSGIServer, self).__init__(socket, application, *args, **kwargs)
            self.handler_class = HTTPServerTestWrapper.MockHandler
            handler = self.handler_class(server=self)
            HTTPServerTestWrapper._server = self

    class MockHttpServer(HTTPServer):
        def __init__(self, wrapper, *args, **kwargs):
            self.wrapper = wrapper
            self.wrapper._http_server = self
            super(HTTPServerTestWrapper.MockHttpServer, self).__init__(*args, **kwargs)
            self.WSGI_SERVER_CLASS = HTTPServerTestWrapper.MockWSGIServer

    def __init__(self, *args, **kwargs):
        self._handler = None
        self._server = None
        self._http_server = None
        self.responses = []

    def create_httpserver(self, *args, **kwargs):
        #creates Mocked HTTPServer
        if self._http_server is not None:
            raise Exception("Wrapper Already Has An Existing Server")
        kwargs["port"] = kwargs.get("port", self.find_free_port())
        kwargs["address"] = kwargs.get("address", "0.0.0.0")
        self._http_server = HTTPServerTestWrapper.MockHttpServer(self, *args, **kwargs)
        self._http_server.register_consumer("hidden_response_queue", Queue(name="hidden_response_queue"))
        return self._http_server

    def send_request(self, method, path="/", host="localhost", headers={}, body=""):
        #inserts mock data into necessary places and kicks off request processing
        #actual requests submitted via mocked server will error
        body = str(body)
        default_headers = {
            "Host": host,
            "Connection": "keep-alive",
            "Accept-Encoding": "gzip, deflate",
            "User-Agent": "python-requests/2.23.0",
            "Content-Length": len(body)
        }
        self._handler.mocked_headers = default_headers
        self._handler.mocked_headers.update(headers)
        self._handler.mocked_method = method
        self._handler.mocked_host = host
        self._handler.mocked_path = path
        self._handler.mocked_content = body
        self._http_server.threads.spawn(self._handler.handle_one_request, restart=False)
        sleep(0)

    def get_response(self, event):
        if len(self.responses) < 1:
            self._http_server.pool.inbound["hidden_response_queue"].put(event)
            sleep(0)
            sleep(0)
            sleep(0)
        return self.responses.pop(0)

    def find_free_port(self,):
        with closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
            s.bind(('', 0))
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            return s.getsockname()[1]

parser = etree.XMLParser(remove_blank_text=True)
#used to ignore formatting differences and focus on basic XML structure
def xml_formatter(xml_str):
    return etree.tostring(etree.XML(xml_str, parser=parser))

#used to ignore formatting differences and focus on basic JSON structure
def json_formatter(json_str):
    return json.dumps(json.loads(json_str))

class TestHTTPServer(unittest.TestCase):
    """
    Actor for testing the response formatting of the HTTP Server

    TODO: It's currently somewhat annoying that you have to manually insert the event_id into the responders dict
    every test. Wrote a decorator that wrapped the test_* methods and did that automatically, but it felt kind of dirty.
    Could re-vist that or a similar idea if repeating gets to annoying
    """
    '''
    Each test should be self contained and capable of passing without other tests
    '''
    def setUp(self):
        self.actor = TestActorWrapper(HTTPServer("actor", address="0.0.0.0", port=8123))

    def tearDown(self):
        self.actor.stop()

    def test_content_type_text_plain(self):
        _input_event = HttpEvent()
        self.actor.actor.responders[_input_event.event_id] = (type(_input_event), self.actor._output_funnel)
        self.actor.input = _input_event
        output = self.actor.output
        self.assertEqual(output.headers['Content-Type'], 'text/plain')

    def test_content_type_json_event(self):
        _input_event = JSONHttpEvent()
        self.actor.actor.responders[_input_event.event_id] = (type(_input_event), self.actor._output_funnel)
        self.actor.input = _input_event
        output = self.actor.output
        self.assertEqual(output.headers['Content-Type'], 'application/json')

    def test_content_type_xml_event(self):
        _input_event = XMLHttpEvent()
        self.actor.actor.responders[_input_event.event_id] = (type(_input_event), self.actor._output_funnel)
        self.actor.input = _input_event
        output = self.actor.output
        self.assertEqual(output.headers['Content-Type'], 'application/xml')

    def test_json_event_formatted_in_data_tag(self):
        expected = {
            "data": {
                "honolulu": "is blue blue"
            }
        }
        _input_event = JSONHttpEvent(data={'honolulu': 'is blue blue'})
        self.actor.actor.responders[_input_event.event_id] = (type(_input_event), self.actor._output_funnel)
        self.actor.input = _input_event
        output = self.actor.output
        self.assertEqual(json.loads(output.body), expected)

    def test_json_event_pagination_links(self):
        expected = {"_pagination": {"next": "/credit_unions/CU00000/places?limit=2&offset=4",
                                    "prev": "/credit_unions/CU00000/places?limit=2&offset=2"},
                    "data": [{"honolulu": "is blue blue"}, {"ohio": "why i go"}]}
        environment = {'PATH_INFO': '/credit_unions/CU00000/places'}

        _input_event = JSONHttpEvent(data=[{'honolulu': 'is blue blue'}, {'ohio': 'why i go'}], environment=environment)
        _input_event._pagination = {'limit': 2, 'offset': 2}
        self.actor.actor.responders[_input_event.event_id] = (type(_input_event), self.actor._output_funnel)
        self.actor.input = _input_event
        output = self.actor.output
        self.assertEqual(json.loads(output.body), expected)


    def test_json_event_pagination_next_link_not_present_if_num_results_less_than_limit(self):
        expected = {"_pagination": {"prev": "/credit_unions/CU00000/places?limit=3&offset=2"},
                    "data": [{"honolulu": "is blue blue"}, {"ohio": "why i go"}]}
        environment = {'PATH_INFO': '/credit_unions/CU00000/places'}

        _input_event = JSONHttpEvent(data=[{'honolulu': 'is blue blue'}, {'ohio': 'why i go'}], environment=environment)
        _input_event._pagination = {'limit': 3, 'offset': 2}
        self.actor.actor.responders[_input_event.event_id] = (type(_input_event), self.actor._output_funnel)
        self.actor.input = _input_event
        output = self.actor.output
        self.assertEqual(json.loads(output.body), expected)
        self.actor.stop()

    def test_service_routing(self):
        routes_config = {"routes":[{"id": "base","path": "/<queue:re:[a-zA-Z_0-9]+?>","method": ["POST"]}]}
        wrapper = HTTPServerTestWrapper()
        actor = wrapper.create_httpserver("http_server", routes_config=routes_config)
        actor.pool.outbound.add("sample_service_1")
        actor.pool.outbound.add("sample_service_2")
        actor.pool.outbound.add("sample_service_3")
        actor.pool.inbound.add("error")
        actor.start()
        data_obj = json.dumps({"data":123})

        #baseline
        assert len(actor.pool.outbound["sample_service_1"]) == 0
        assert len(actor.pool.outbound["sample_service_2"]) == 0
        assert len(actor.pool.outbound["sample_service_3"]) == 0
        assert len(actor.pool.inbound["error"]) == 0

        #missing queue
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"application/json"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service_1"]) == 0
        assert len(actor.pool.outbound["sample_service_2"]) == 0
        assert len(actor.pool.outbound["sample_service_3"]) == 0
        assert len(actor.pool.inbound["error"]) == 1

        #sample_service_1
        wrapper.send_request(method="POST", path="/sample_service_1", headers={"Content-Type":"application/json"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service_1"]) == 1
        assert len(actor.pool.outbound["sample_service_2"]) == 0
        assert len(actor.pool.outbound["sample_service_3"]) == 0
        assert len(actor.pool.inbound["error"]) == 1

        #sample_service_2
        wrapper.send_request(method="POST", path="/sample_service_2", headers={"Content-Type":"application/json"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service_1"]) == 1
        assert len(actor.pool.outbound["sample_service_2"]) == 1
        assert len(actor.pool.outbound["sample_service_3"]) == 0
        assert len(actor.pool.inbound["error"]) == 1

        #sampl_service_3
        wrapper.send_request(method="POST", path="/sample_service_3", headers={"Content-Type":"application/json"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service_1"]) == 1
        assert len(actor.pool.outbound["sample_service_2"]) == 1
        assert len(actor.pool.outbound["sample_service_3"]) == 1
        assert len(actor.pool.inbound["error"]) == 1

        actor.stop()

    def test_content_type(self):
        routes_config = {"routes":[{"id": "base","path": "/<queue:re:[a-zA-Z_0-9]+?>","method": ["POST"]}]}
        wrapper = HTTPServerTestWrapper()
        actor = wrapper.create_httpserver("http_server", routes_config=routes_config)
        actor.pool.outbound.add("sample_service")
        actor.pool.inbound.add("error")
        actor.start()

        #application/json
        assert len(actor.pool.outbound["sample_service"]) == 0
        data_obj = json.dumps({"data":123})
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"application/json"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, JSONHttpEvent)
        assert json_formatter(event.data_string()) == json_formatter(data_obj)

        #ATTENTION
        #application/json+schema
        #should fail given logic in ContentTypePlugin
        #however the current ContentTypePlugin implementation only applies to the first request submitted to HttpServer
        #these tests would not be true if placed before prior content-type check
        assert len(actor.pool.outbound["sample_service"]) == 0
        data_obj = json.dumps({"data":123})
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"application/json+schema"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, JSONHttpEvent)
        assert json_formatter(event.data_string()) == json_formatter(data_obj)

        #application/json
        #with xml/invalid input
        assert len(actor.pool.outbound["sample_service"]) == 0
        assert len(actor.pool.inbound["error"]) == 0
        data_obj = "<data>123</data>"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"application/json"}, body=data_obj)
        assert len(actor.pool.inbound["error"]) == 1
        event = actor.pool.inbound["error"].get(block=True)
        assert isinstance(event.error, InvalidEventDataModification)

        #application/xml+schema
        #should fail (but doesn't) similar to application/json+schema
        assert len(actor.pool.outbound["sample_service"]) == 0
        data_obj = "<data>123</data>"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"application/xml+schema"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, XMLHttpEvent)
        assert xml_formatter(event.data_string()) == xml_formatter(data_obj)

        #application/xml
        assert len(actor.pool.outbound["sample_service"]) == 0
        data_obj = "<data>123</data>"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"application/xml"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, XMLHttpEvent)
        assert xml_formatter(event.data_string()) == xml_formatter(data_obj)

        #text/plain
        assert len(actor.pool.outbound["sample_service"]) == 0
        data_obj = "some random string"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"text/plain"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, HttpEvent)
        assert event.data_string() == data_obj

        #text/html
        assert len(actor.pool.outbound["sample_service"]) == 0
        data_obj = "<data>123</data>"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"text/html"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, XMLHttpEvent)
        assert xml_formatter(event.data_string()) == xml_formatter(data_obj)

        #text/xml
        assert len(actor.pool.outbound["sample_service"]) == 0
        data_obj = "<data>123</data>"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"text/xml"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, XMLHttpEvent)
        assert xml_formatter(event.data_string()) == xml_formatter(data_obj)

        #text/xml
        #with json/invalid data
        assert len(actor.pool.outbound["sample_service"]) == 0
        assert len(actor.pool.inbound["error"]) == 0
        data_obj = json.dumps({"data":123})
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"text/xml"}, body=data_obj)
        assert len(actor.pool.inbound["error"]) == 1
        event = actor.pool.inbound["error"].get(block=True)
        assert isinstance(event.error, InvalidEventDataModification)
        
        #application/x-www-form-urlencoded
        #with XML data
        assert len(actor.pool.outbound["sample_service"]) == 0
        data_obj = "XML=<data>123</data>"
        data_obj2 = "<data>123</data>"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"application/x-www-form-urlencoded"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, XMLHttpEvent)
        assert xml_formatter(event.data_string()) == xml_formatter(data_obj2)

        #application/x-www-form-urlencoded
        #with JSON data
        assert len(actor.pool.outbound["sample_service"]) == 0
        data_obj2 = json.dumps({"data":123})
        data_obj = "JSON=%s" % data_obj2
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"application/x-www-form-urlencoded"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, JSONHttpEvent)
        assert json_formatter(event.data_string()) == json_formatter(data_obj2)

        #ATTENTION
        #application/x-www-form-urlencoded
        #with form data
        #this doesn't seem right
        assert len(actor.pool.outbound["sample_service"]) == 0
        data_obj = "parm1=value1&parm2=value2"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"application/x-www-form-urlencoded"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, HttpEvent)
        assert event.data_string() == "value2"
        #I think one of these should be true
        #assert event.data_string() == data_obj
        #assert json_formatter(event.data_string()) == json_formatter(json.dumps({"parm1":"value1","parm2":value2"}))

        #ATTENTION
        #application/x-www-form-urlencoded
        #with string data
        #this doesn't seem right
        #I think this should through an error
        assert len(actor.pool.outbound["sample_service"]) == 0
        data_obj = "some random string"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":"application/x-www-form-urlencoded"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, HttpEvent)
        assert event.data_string() == 'None'

        #ATTENTION
        #No Content-Type
        #with string data
        #content-type defaults to JSONHttpEvent
        #I'm thinking this should be HttpEvent
        assert len(actor.pool.outbound["sample_service"]) == 0
        assert len(actor.pool.inbound["error"]) == 0
        data_obj = "some random string"
        wrapper.send_request(method="POST", path="/sample_service", headers={}, body=data_obj)
        assert len(actor.pool.inbound["error"]) == 1
        event = actor.pool.inbound["error"].get(block=True)
        assert isinstance(event, JSONHttpEvent)
        assert isinstance(event.error, InvalidEventDataModification)

        #ATTENTION
        #No Content-Type
        #with json data
        #content-type defaults to JSONHttpEvent
        #I'm thinking this should be HttpEvent
        #Also this should fail if ContentTypePlugin worked correctly
        assert len(actor.pool.outbound["sample_service"]) == 0
        data_obj = json.dumps({"data":123})
        wrapper.send_request(method="POST", path="/sample_service", headers={}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, JSONHttpEvent)
        assert json_formatter(event.data_string()) == json_formatter(data_obj)

        actor.stop()

    def test_accepts(self):
        '''
            Not testing conversions just that conversion occur
        '''
        routes_config = {"routes":[{"id": "base","path": "/<queue:re:[a-zA-Z_0-9]+?>","method": ["POST"]}]}
        wrapper = HTTPServerTestWrapper()
        actor = wrapper.create_httpserver("http_server", routes_config=routes_config)
        actor.pool.outbound.add("sample_service")
        
        actor.start()

        #content_type = application/json
        #accept = None
        #response_event = JSONHttpEvent
        data_obj = json.dumps({"data":123})
        content_type = "application/json"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":content_type}, body=data_obj)
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, JSONHttpEvent)
        headers, data, _, _ = wrapper.get_response(event=event)
        assert headers["Content-Type"] == content_type
        assert json_formatter(data) == json_formatter(data_obj)

        #content_type = application/json
        #accept = application/xml
        #response_event = JSONHttpEvent
        data_obj = json.dumps({"data":123})
        content_type, accept = "application/json", "application/xml"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":content_type, "Accept":accept}, body=data_obj)
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, JSONHttpEvent)
        headers, data, _, _ = wrapper.get_response(event=event)
        assert headers["Content-Type"] == accept
        event = XMLHttpEvent()
        event.data = json.loads(data_obj)
        assert xml_formatter(data) == xml_formatter(event.data_string())

        #ATTENTION
        #content_type = application/json
        #accept = text/plain
        #response_event = JSONHttpEvent
        data_obj = json.dumps({"data":123})
        content_type, accept = "application/json", "text/plain"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":content_type, "Accept":accept}, body=data_obj)
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, JSONHttpEvent)
        headers, data, _, _ = wrapper.get_response(event=event)
        #should this not be 'text/plain'
        #I understand there is no good way to convert json to plain text (other than json as a string) so maybe just 'SUCCESS'/'ERROR'??
        #Regardless of data I think the header should be this
        #assert headers["Content-Type"] == accept
        assert headers["Content-Type"] == content_type
        assert json_formatter(data) == json_formatter(data_obj)

        #ATTENTION
        #content_type = application/json
        #accept = text/html
        #response_event = JSONHttpEvent
        data_obj = json.dumps({"data":123})
        content_type, accept = "application/json", "application/xml"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type":content_type, "Accept":accept}, body=data_obj)
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, JSONHttpEvent)
        headers, data, _, _ = wrapper.get_response(event=event)
        assert headers["Content-Type"] == accept
        #XML and HTML are not necessarily the same maybe a new HTMLEvent down the road?
        event = XMLHttpEvent()
        event.data = json.loads(data_obj)
        assert xml_formatter(data) == xml_formatter(event.data_string())
        
        #ATTENTION
        #content_type = None
        #accept = application/json
        #response_event = JSONHttpEvent
        #this should return error but doesn't due to ContentTypePlugin not being a decorator
        data_obj = json.dumps({"data":123})
        accept = "application/json"
        wrapper.send_request(method="POST", path="/sample_service", headers={"Accept":accept}, body=data_obj)
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, JSONHttpEvent)
        headers, data, _, _ = wrapper.get_response(event=event)
        assert headers["Content-Type"] == accept
        assert json_formatter(data) == json_formatter(data_obj)

        #ATTENTION
        #content_type = None
        #accept = None
        #response_event = JSONHttpEvent
        #this should return error but doesn't due to ContentTypePlugin not being a decorator
        data_obj = json.dumps({"data":123})
        accept = "application/json"
        wrapper.send_request(method="POST", path="/sample_service", headers={}, body=data_obj)
        event = actor.pool.outbound["sample_service"].get(block=True)
        assert isinstance(event, JSONHttpEvent)
        headers, data, _, _ = wrapper.get_response(event=event)
        assert headers["Content-Type"] == accept
        assert json_formatter(data) == json_formatter(data_obj)
        actor.stop()

    def test_response_data_wrapper(self):
        routes_config = {"routes":[{"id": "base","path": "/<queue:re:[a-zA-Z_0-9]+?>","method": ["POST"]}]}
        wrapper = HTTPServerTestWrapper()
        actor = wrapper.create_httpserver("http_server", routes_config=routes_config)
        actor.pool.outbound.add("sample_service")
        
        actor.start()

        #default add wrapper
        data_obj = json.dumps([1,2,3])
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type": "application/json"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        headers, data, _, _ = wrapper.get_response(event=event)
        assert json_formatter(data) != json_formatter(data_obj)
        assert json_formatter(data) == json_formatter(json.dumps({"data":[1,2,3]}))

        data_obj = json.dumps({"temp": 213})
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type": "application/json"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        headers, data, _, _ = wrapper.get_response(event=event)
        assert json_formatter(data) != json_formatter(data_obj)
        assert json_formatter(data) == json_formatter(json.dumps({"data":{"temp": 213}}))

        data_obj = json.dumps({"temp": 213, "data": 123})
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type": "application/json"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        headers, data, _, _ = wrapper.get_response(event=event)
        assert json_formatter(data) != json_formatter(data_obj)
        assert json_formatter(data) == json_formatter(json.dumps({"data":{"temp": 213, "data": 123}}))

        #default ignore case
        data_obj = json.dumps({"data": 213})
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type": "application/json"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        headers, data, _, _ = wrapper.get_response(event=event)
        assert json_formatter(data) == json_formatter(data_obj)
        
        #ignore wrapper variable
        data_obj = json.dumps([1,2,3])
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type": "application/json"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        event = actor.pool.outbound["sample_service"].get(block=True)
        event.set("use_response_wrapper", False)
        headers, data, _, _ = wrapper.get_response(event=event)
        assert json_formatter(data) == json_formatter(data_obj)

        actor.stop()

    def test_wsgi_plugins(self):
        '''
            This is a test of the built in plugin functionality
            Use this to help understand what a plugin should look like
        '''
        class TestPlugin1(object):
            def __init__(self, actor, *args, **kwargs):
                self.actor = actor
            def apply(self, callback, route):
                def callback_wrapper(*args, **kwargs):
                    self.actor.test_plugin_1 = True
                    return callback(*args, **kwargs)
                return callback_wrapper
        class TestPlugin2(object):
            def __init__(self, actor, *args, **kwargs):
                self.actor = actor
            def apply(self, callback, route):
                def callback_wrapper(*args, **kwargs):
                    self.actor.test_plugin_2 = True
                    return callback(*args, **kwargs)
                return callback_wrapper

        routes_config = {"routes":[{"id": "base","path": "/<queue:re:[a-zA-Z_0-9]+?>","method": ["POST"]}]}
        wrapper = HTTPServerTestWrapper()
        actor = wrapper.create_httpserver("http_server", routes_config=routes_config)
        actor.pool.outbound.add("sample_service")
        actor.test_plugin_1, actor.test_plugin_2 = False, False
        actor.start()

        data_obj = json.dumps({"data":123})
        #pre install test
        assert not actor.test_plugin_1 and not actor.test_plugin_2 == True
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type": "application/json"}, body=data_obj)
        assert len(actor.pool.outbound["sample_service"]) == 1
        assert not actor.test_plugin_1 and not actor.test_plugin_2 == True

        #install plugins
        actor.wsgi_app.install(TestPlugin1(actor=actor))
        actor.wsgi_app.install(TestPlugin2(actor=actor))

        #test after 1 submission
        actor.test_plugin_1, actor.test_plugin_2 = False, False
        assert not actor.test_plugin_1 and not actor.test_plugin_2 == True
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type": "application/json"}, body=data_obj)
        assert actor.test_plugin_1 and actor.test_plugin_2 == True
        
        #test after 2 submissions
        actor.test_plugin_1, actor.test_plugin_2 = False, False
        assert not actor.test_plugin_1 and not actor.test_plugin_2 == True
        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type": "application/json"}, body=data_obj)
        assert actor.test_plugin_1 and actor.test_plugin_2 == True
    
    def test_bottle_error_handling(self):
        routes_config = {"routes":[{"id": "base","path": "/<queue:re:[a-zA-Z_0-9]+?>","method": ["POST"]}]}
        wrapper = HTTPServerTestWrapper()
        actor = wrapper.create_httpserver("http_server", routes_config=routes_config)
        actor.pool.outbound.add("sample_service")
        actor.start()

        data_obj = "doesn't matter"

        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type": "radom/mime-type"}, body=data_obj)
        headers, data, status, _ = wrapper.get_response(event=None)
        assert headers["Content-Type"] == "text/html; charset=UTF-8"
        assert data.strip("\n").strip().startswith("<!DOCTYPE HTML PUBLIC")
        assert status == 415

        wrapper.send_request(method="GET", path="/sample_service", headers={"Content-Type": "application/json", "Accept": "application/xml"}, body=data_obj)
        headers, data, status, _ = wrapper.get_response(event=None)
        assert headers["Content-Type"] == "text/html; charset=UTF-8"
        assert data.strip("\n").strip().startswith("<!DOCTYPE HTML PUBLIC")
        assert status == 405
        
        wrapper.send_request(method="POST", path="/test/sample_service", headers={"Content-Type": "application/json"}, body=data_obj)
        headers, data, status, _ = wrapper.get_response(event=None)
        assert headers["Content-Type"] == "text/html; charset=UTF-8"
        assert data.strip("\n").strip().startswith("<!DOCTYPE HTML PUBLIC")
        assert status == 404
        
        actor.stop()

        routes_config = {"routes":[{"id": "base","path": "/<queue:re:[a-zA-Z_0-9]+?>","method": ["POST"]}]}
        wrapper = HTTPServerTestWrapper()
        actor = wrapper.create_httpserver("http_server", routes_config=routes_config, process_bottle_exceptions=True)
        actor.pool.outbound.add("sample_service")
        actor.start()

        data_obj = "doesn't matter"

        wrapper.send_request(method="POST", path="/sample_service", headers={"Content-Type": "radom/mime-type"}, body=data_obj)
        headers, data, status, _ = wrapper.get_response(event=None)
        assert headers["Content-Type"] == "text/plain"
        assert data == '[{\'override\': None, \'message\': "Unsupported Content-Type \'radom/mime-type\'", \'code\': None}]'
        #ATTENTION
        #I would think this should be true
        #assert data == "Unsupported Content-Type 'radom/mime-type'"
        assert status == 415

        wrapper.send_request(method="GET", path="/sample_service", headers={"Content-Type": "application/json", "Accept": "application/xml"}, body=data_obj)
        headers, data, status, _ = wrapper.get_response(event=None)
        assert headers["Content-Type"] == "application/xml"
        assert data == etree.tostring(etree.fromstring("<errors><error><message>Method not allowed.</message></error></errors>"))
        assert status == 405
        
        wrapper.send_request(method="POST", path="/test/sample_service", headers={"Content-Type": "application/json", "Accept": "application/json"}, body=data_obj)
        headers, data, status, _ = wrapper.get_response(event=None)
        assert headers["Content-Type"] == "application/json"
        assert data == json.dumps({"errors": [{'override': None, 'message': "Not found: \'/test/sample_service\'", 'code': None}]})
        assert status == 404

        actor.stop()

    def _test_manual(self):
        routes_config = {"routes":[{"id": "base","path": "/<queue:re:[a-zA-Z_0-9]+?>","method": ["POST"]}]}
        actor = HTTPServer("http_server", port=34567, address="0.0.0.0", routes_config=routes_config)
        actor.pool.outbound.add("sample_service")
        actor.start()


        response = requests.post("http://localhost:34567/sample_service", headers={}, data="some text")
        print response.text
