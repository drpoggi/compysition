import json
from lxml import etree
import unittest
import requests

#compysition imports
from compysition.actors.httpserver import HTTPServer
from compysition.event import (JSONHttpEvent, HttpEvent, XMLHttpEvent, _XWWWFORMHttpEvent, _XMLXWWWFORMHttpEvent,
    _JSONXWWWFORMHttpEvent)
from compysition.queue import Queue as CQueue
from compysition.errors import InvalidEventDataModification
from compysition.util import PY2, try_decode, iteritems

#compysition test imports
from compysition.testutils.test_actor import _TestActorWrapper
from compysition.testutils.httpserver import *

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
        self.actor = _TestActorWrapper(HTTPServer("actor", address="0.0.0.0", port=8123))

    def tearDown(self):
        self.actor.stop()

    def test_content_type_text_plain(self):
        _input_event = HttpEvent()
        self.actor.actor.responders[_input_event.event_id] = (type(_input_event), self.actor._output_funnel, ["*/*"])
        self.actor.input = _input_event
        output = self.actor.output
        self.assertEqual(output.headers['Content-Type'], 'text/plain')

    def test_content_type_json_event(self):
        _input_event = JSONHttpEvent()
        self.actor.actor.responders[_input_event.event_id] = (type(_input_event), self.actor._output_funnel, ["*/*"])
        self.actor.input = _input_event
        output = self.actor.output
        self.assertEqual(output.headers['Content-Type'], 'application/json')

    def test_content_type_xml_event(self):
        _input_event = XMLHttpEvent()
        self.actor.actor.responders[_input_event.event_id] = (type(_input_event), self.actor._output_funnel, ["*/*"])
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
        self.actor.actor.responders[_input_event.event_id] = (type(_input_event), self.actor._output_funnel, ["*/*"])
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
        self.actor.actor.responders[_input_event.event_id] = (type(_input_event), self.actor._output_funnel, ["*/*"])
        self.actor.input = _input_event
        output = self.actor.output
        self.assertEqual(json.loads(output.body), expected)


    def test_json_event_pagination_next_link_not_present_if_num_results_less_than_limit(self):
        expected = {"_pagination": {"prev": "/credit_unions/CU00000/places?limit=3&offset=2"},
                    "data": [{"honolulu": "is blue blue"}, {"ohio": "why i go"}]}
        environment = {'PATH_INFO': '/credit_unions/CU00000/places'}

        _input_event = JSONHttpEvent(data=[{'honolulu': 'is blue blue'}, {'ohio': 'why i go'}], environment=environment)
        _input_event._pagination = {'limit': 3, 'offset': 2}
        self.actor.actor.responders[_input_event.event_id] = (type(_input_event), self.actor._output_funnel, ["*/*"])
        self.actor.input = _input_event
        output = self.actor.output
        self.assertEqual(json.loads(output.body), expected)
        self.actor.stop()

class TestHTTPServerAlt(unittest.TestCase):

    def _get_event(self, queue_name, pool_name="outbound", event_class=JSONHttpEvent):
        '''
            Validates that an event exists on the target queue.
            Retrieves said event and validates that all queues are now empty
            -- assumes use of create_test_server decorator
        '''
        queue = getattr(self.server_actor.pool, pool_name)[queue_name]
        assert len(queue) > 0
        event = queue.get()
        assert event.__class__ == event_class
        self._check_empty()
        return event

    def _check_empty(self, ignore_queues=[]):
        '''
            Validates that all inbound and outbound queues are empty
            -- assumes use of create_test_server decorator
        '''
        pool_names = ("outbound", "inbound")
        for pool_name in pool_names:
            pool = getattr(self.server_actor.pool, pool_name)
            for _, queue in iteritems(pool):
                assert len(queue) == 0

    def _send_timeout_mock_request(self, *args, **kwargs):
        '''
            Simple func to wrap send_mock_request in an assertRaises
        '''
        with self.assertRaises(MockTimeoutException):
            send_mock_request(*args, **kwargs)

    @create_test_server(outbound_queues=['sample_service_1', 'sample_service_2', 'sample_service_3'], start=False)
    def test_service_routing(self, base_kwargs):
        request_kwargs = dict(base_kwargs, **{"data": json.dumps({"data":123}), "headers": {"Content-Type": "application/json"}})
        request_kwargs.pop("url", None)

        #baseline
        self._check_empty()

        #missing queue
        self._send_timeout_mock_request(url="http://localhost:34567/sample_service", **request_kwargs)
        self._get_event(queue_name="error", pool_name="inbound")

        #sample_service_1
        self._send_timeout_mock_request(url="http://localhost:34567/sample_service_1", **request_kwargs)
        self._get_event(queue_name="sample_service_1")

        #sample_service_2
        self._send_timeout_mock_request(url="http://localhost:34567/sample_service_2", **request_kwargs)
        self._get_event(queue_name="sample_service_2")

        #sample_service_3
        self._send_timeout_mock_request(url="http://localhost:34567/sample_service_3", **request_kwargs)
        self._get_event(queue_name="sample_service_3")

    @create_test_server(outbound_queues=['sample_service'], start=False)
    def test_content_type(self, base_kwargs):

        #baseline
        self._check_empty()

        #application/json
        kwargs = dict(base_kwargs, **{"data": json.dumps({"data":123}), "headers": {"Content-Type":"application/json"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        assert json_formatter(event.data_string()) == json_formatter(kwargs["data"])

        #ATTENTION
        #application/json+schema
        #should fail given logic in ContentTypePlugin
        #however the current ContentTypePlugin implementation only applies to the first request submitted to HttpServer
        #these tests would not be true if placed before prior content-type check
        kwargs = dict(base_kwargs, **{"data": json.dumps({"data":123}), "headers": {"Content-Type":"application/json+schema"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        assert json_formatter(event.data_string()) == json_formatter(kwargs["data"])

        #application/json
        #with xml/invalid input
        kwargs = dict(base_kwargs, **{"data": "<data>123</data>", "headers": {"Content-Type":"application/json"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="error", pool_name="inbound")
        assert isinstance(event.error, InvalidEventDataModification)

        #application/xml+schema
        #should fail (but doesn't) similar to application/json+schema
        kwargs = dict(base_kwargs, **{"data": "<data>123</data>", "headers": {"Content-Type":"application/xml+schema"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service", event_class=XMLHttpEvent)
        assert xml_formatter(event.data_string()) == xml_formatter(kwargs["data"])

        #application/xml
        kwargs = dict(base_kwargs, **{"data": "<data>123</data>", "headers": {"Content-Type":"application/xml"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service", event_class=XMLHttpEvent)
        assert xml_formatter(event.data_string()) == xml_formatter(kwargs["data"])

        #text/plain
        kwargs = dict(base_kwargs, **{"data": "some random string", "headers": {"Content-Type":"text/plain"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service", event_class=HttpEvent)
        assert event.data_string() == kwargs["data"]

        #text/html
        kwargs = dict(base_kwargs, **{"data": "<data>123</data>", "headers": {"Content-Type":"text/html"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service", event_class=XMLHttpEvent)
        assert xml_formatter(event.data_string()) == xml_formatter(kwargs["data"])

        #text/xml
        kwargs = dict(base_kwargs, **{"data": "<data>123</data>", "headers": {"Content-Type":"text/xml"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service", event_class=XMLHttpEvent)
        assert xml_formatter(event.data_string()) == xml_formatter(kwargs["data"])

        #text/xml
        #with json/invalid data
        kwargs = dict(base_kwargs, **{"data": json.dumps({"data":123}), "headers": {"Content-Type":"text/xml"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="error", pool_name="inbound", event_class=XMLHttpEvent)
        assert isinstance(event.error, InvalidEventDataModification)

        #application/x-www-form-urlencoded
        #with XML data
        kwargs = dict(base_kwargs, **{"data": "XML=<data>123</data>", "headers": {"Content-Type":"application/x-www-form-urlencoded"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service", event_class=XMLHttpEvent)
        assert xml_formatter(event.data_string()) == xml_formatter("<data>123</data>")

        #application/x-www-form-urlencoded
        #with JSON data
        kwargs = dict(base_kwargs, **{"data": "JSON={}".format(json.dumps({"data":123})), "headers": {"Content-Type":"application/x-www-form-urlencoded"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        assert json_formatter(event.data_string()) == json_formatter(json.dumps({"data":123}))

        #ATTENTION
        #application/x-www-form-urlencoded
        #with form data
        kwargs = dict(base_kwargs, **{"data": "parm1=value1&parm2=value2", "headers": {"Content-Type":"application/x-www-form-urlencoded"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service", event_class=_XWWWFORMHttpEvent)
        assert event.data_string() == "parm1=value1&parm2=value2"
        event = event.convert(JSONHttpEvent)
        assert event.__class__ == JSONHttpEvent
        assert event.data_string() == '{"parm1": "value1", "parm2": "value2"}'

        #ATTENTION
        #application/x-www-form-urlencoded
        #with string data
        kwargs = dict(base_kwargs, **{"data": "some random string", "headers": {"Content-Type":"application/x-www-form-urlencoded"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="error", pool_name="inbound", event_class=_XWWWFORMHttpEvent)
        assert event.data_string() == ""
        py2_error = 'error=Malformed%20data%3A%20need%20more%20than%201%20value%20to%20unpack'
        py3_error = 'error=Malformed%20data%3A%20not%20enough%20values%20to%20unpack%20%28expected%202%2C%20got%201%29'
        assert event.error_string() == py2_error if PY2 else py3_error

        #ATTENTION
        #No Content-Type
        #with string data
        #content-type defaults to JSONHttpEvent
        #I'm thinking this should be HttpEvent
        kwargs = dict(base_kwargs, **{"data": "some random string", "headers": {}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="error", pool_name="inbound")
        assert isinstance(event.error, InvalidEventDataModification)

        #ATTENTION
        #No Content-Type
        #with json data
        #content-type defaults to JSONHttpEvent
        #I'm thinking this should be HttpEvent
        #Also this should fail if ContentTypePlugin worked correctly
        kwargs = dict(base_kwargs, **{"data": json.dumps({"data":123}), "headers": {}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        assert json_formatter(event.data_string()) == json_formatter(kwargs["data"])

    @create_test_server(outbound_queues=['sample_service'], start=False, use_jx_xwwwform_events=True)
    def test_jx_xwwwform_content_types(self, base_kwargs):

        #baseline
        self._check_empty()

        #application/x-www-form-urlencoded
        #with XML data
        kwargs = dict(base_kwargs, **{"data": 'XML=%3Cdata%3E123%3C%2Fdata%3E', "headers": {"Content-Type":"application/x-www-form-urlencoded"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service", event_class=_XMLXWWWFORMHttpEvent)
        assert event.data_string() == 'XML=%3Cdata%3E123%3C%2Fdata%3E'
        event = event.convert(XMLHttpEvent)
        assert event.__class__ == XMLHttpEvent and event.data_string() == "<data>123</data>"

        #application/x-www-form-urlencoded
        #with XML data and other random data
        kwargs = dict(base_kwargs, **{"data": 'XML=%3Cdata%3E123%3C%2Fdata%3E&sample=123', "headers": {"Content-Type":"application/x-www-form-urlencoded"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service", event_class=_XMLXWWWFORMHttpEvent)
        assert event.data_string() == 'XML=%3Cdata%3E123%3C%2Fdata%3E'
        event = event.convert(XMLHttpEvent)
        assert event.__class__ == XMLHttpEvent and event.data_string() == "<data>123</data>"

        #application/x-www-form-urlencoded
        #with JSON data
        kwargs = dict(base_kwargs, **{"data": "JSON=%7B%22data%22%3A%20123%7D", "headers": {"Content-Type":"application/x-www-form-urlencoded"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service", event_class=_JSONXWWWFORMHttpEvent)
        assert event.data_string() == "JSON=%7B%22data%22%3A%20123%7D"
        event = event.convert(JSONHttpEvent)
        assert event.__class__ == JSONHttpEvent and event.data_string() == json.dumps({"data":123})

    @create_test_server(outbound_queues=['sample_service'])
    def test_accepts(self, base_kwargs, base_resp_kwargs):
        '''
            Not testing conversions just that conversion occur
        '''

        #content_type = application/json
        #accept = None
        kwargs = dict(base_kwargs, **{"data": json.dumps({"data":123}), "headers": {"Content-Type":"application/json"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        headers, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        assert headers["Content-Type"] == kwargs['headers']['Content-Type']
        assert json_formatter(data) == json_formatter(kwargs['data'])

        #content_type = application/json
        #accept = application/xml
        kwargs = dict(base_kwargs, **{"data": json.dumps({"data":123}), "headers": {"Content-Type":"application/json", "Accept": "application/xml"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        print(event)
        headers, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        print(data)
        assert headers["Content-Type"] == kwargs['headers']['Accept']
        assert xml_formatter("<data>123</data>") == xml_formatter(data)

        #ATTENTION
        #content_type = application/json
        #accept = text/plain
        kwargs = dict(base_kwargs, **{"data": json.dumps({"data":123}), "headers": {"Content-Type":"application/json", "Accept": "text/plain"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        headers, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        assert headers["Content-Type"] == kwargs['headers']['Content-Type']
        assert json_formatter(data) == json_formatter(kwargs["data"])
        #should this not be 'text/plain'
        #I understand there is no good way to convert json to plain text (other than json as a string) so maybe just 'SUCCESS'/'ERROR'??
        #Regardless of data I think the header should be this
        #assert headers["Content-Type"] == kwargs['headers']['Accept']

        #ATTENTION
        #content_type = application/json
        #accept = text/html
        kwargs = dict(base_kwargs, **{"data": json.dumps({"data":123}), "headers": {"Content-Type":"application/json", "Accept": "text/html"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        headers, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        assert headers["Content-Type"] == 'application/xml'
        assert xml_formatter(data) == xml_formatter("<data>123</data>")

        #ATTENTION
        #content_type = None
        #accept = application/json
        #this should return error but doesn't due to ContentTypePlugin not being a decorator
        kwargs = dict(base_kwargs, **{"data": json.dumps({"data":123}), "headers": {"Accept": "application/json"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        headers, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        assert headers["Content-Type"] == kwargs['headers']['Accept']
        assert json_formatter(data) == json_formatter(json.dumps({"data":123}))

        #ATTENTION
        #content_type = None
        #accept = None
        #response_event = JSONHttpEvent
        #this should return error but doesn't due to ContentTypePlugin not being a decorator
        kwargs = dict(base_kwargs, **{"data": json.dumps({"data":123}), "headers": {}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        headers, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        assert headers["Content-Type"] == "application/json"
        assert json_formatter(data) == json_formatter(json.dumps({"data":123}))

    @create_test_server(outbound_queues=['sample_service'], routes_config={"routes":[{"id": "base", "path": "/<queue:re:[a-zA-Z_0-9]+?>", "method": ["POST"], "accept_types": ["application/json"]}]})
    def test_accepts_service_based(self, base_kwargs, base_resp_kwargs):

        #test service based accept type speicifying
        kwargs = dict(base_kwargs, **{"data": "<root>123</root>", "headers": {"Content-Type":"application/xml", "Accept": "application/xml, application/json"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service", event_class=XMLHttpEvent)
        headers, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        assert headers["Content-Type"] == "application/json"
        assert json_formatter(data) == json_formatter(json.dumps({"data":{"root": "123"}}))

    @create_test_server(outbound_queues=['sample_service'])
    def test_response_data_wrapper(self, base_kwargs, base_resp_kwargs):

        #default add wrapper
        kwargs = dict(base_kwargs, **{"data": json.dumps([1,2,3]), "headers": {"Content-Type": "application/json"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        _, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        assert json_formatter(data) == json_formatter(json.dumps({"data":[1,2,3]}))

        kwargs = dict(base_kwargs, **{"data": json.dumps({"temp": 213}), "headers": {"Content-Type": "application/json"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        _, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        assert json_formatter(data) == json_formatter(json.dumps({"data":{"temp": 213}}))

        kwargs = dict(base_kwargs, **{"data": json.dumps({"temp": 213, "data": 123}), "headers": {"Content-Type": "application/json"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        _, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        assert json_formatter(data) == json_formatter(json.dumps({"data":{"temp": 213, "data": 123}}))

        #default ignore case
        kwargs = dict(base_kwargs, **{"data": json.dumps({"data": 213}), "headers": {"Content-Type": "application/json"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        _, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        assert json_formatter(data) == json_formatter(kwargs['data'])
        
        #ignore wrapper variable
        kwargs = dict(base_kwargs, **{"data": json.dumps([1,2,3]), "headers": {"Content-Type": "application/json"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service")
        event.set("use_response_wrapper", False)
        _, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        assert json_formatter(data) == json_formatter(kwargs['data'])

    @create_test_server(outbound_queues=['error'])
    def test_wsgi_plugins(self, base_kwargs):
        '''
            This is a test of the built in plugin functionality
            Use this to help understand what a plugin should look like
        '''
        class _TestPlugin(object):
            def __init__(self, actor, *args, **kwargs):
                self.actor = actor
            def apply(self, callback, route):
                def callback_wrapper(*args, **kwargs):
                    setattr(self.actor, self.var_name, True)
                    return callback(*args, **kwargs)
                return callback_wrapper
        class TestPlugin1(_TestPlugin):
            var_name = 'test_plugin_1'
        class TestPlugin2(_TestPlugin):
            var_name = 'test_plugin_2'

        #setup
        kwargs = dict(base_kwargs, **{"data": json.dumps([1,2,3]), "headers": {"Content-Type": "application/json"}})
        self.server_actor.test_plugin_1 = self.server_actor.test_plugin_2 = False

        #pre install test
        _, data, _, _ = send_mock_request(**kwargs)
        assert self.server_actor.test_plugin_1 or self.server_actor.test_plugin_2 == False

        #install plugins
        self.server_actor.wsgi_app.install(TestPlugin1(actor=self.server_actor))
        self.server_actor.wsgi_app.install(TestPlugin2(actor=self.server_actor))

        #test after 1 submission
        _, data, _, _ = send_mock_request(**kwargs)
        assert self.server_actor.test_plugin_1 and self.server_actor.test_plugin_2 == True

        #test after 2 submissions
        self.server_actor.test_plugin_1 = self.server_actor.test_plugin_2 = False
        _, data, _, _ = send_mock_request(**kwargs)
        assert self.server_actor.test_plugin_1 and self.server_actor.test_plugin_2 == True

    @create_test_server(outbound_queues=['error'])
    def test_bottle_error_handling_baseline(self, base_kwargs):
        base_kwargs = dict(base_kwargs, **{'data': "doesn't matter"})

        kwargs = dict(base_kwargs, **{'headers': {"Content-Type": "radom/mime-type"}})
        headers, data, status, _ = send_mock_request(**kwargs)
        assert headers["Content-Type"] == "text/html; charset=UTF-8"
        assert data.strip("\n").strip().startswith("<!DOCTYPE HTML PUBLIC")
        assert status == 415

        kwargs = dict(base_kwargs, **{'method': 'GET', 'headers': {"Content-Type": "application/json", "Accept": "application/xml"}})
        headers, data, status, _ = send_mock_request(**kwargs)
        assert headers["Content-Type"] == "text/html; charset=UTF-8"
        assert data.strip("\n").strip().startswith("<!DOCTYPE HTML PUBLIC")
        assert status == 405

        kwargs = dict(base_kwargs, **{'url': 'http://localhost:34567/test/sample_service', 'headers': {"Content-Type": "application/json"}})
        headers, data, status, _ = send_mock_request(**kwargs)
        assert headers["Content-Type"] == "text/html; charset=UTF-8"
        assert data.strip("\n").strip().startswith("<!DOCTYPE HTML PUBLIC")
        assert status == 404

    @create_test_server(outbound_queues=['error'], process_bottle_exceptions=True)
    def test_bottle_error_handling(self, base_kwargs):
        base_kwargs = dict(base_kwargs, **{'data': "doesn't matter"})

        kwargs = dict(base_kwargs, **{'headers': {"Content-Type": "radom/mime-type"}})
        headers, data, status, _ = send_mock_request(**kwargs)
        assert headers["Content-Type"] == "text/plain"
        py2_data = '[{\'override\': None, \'message\': "Unsupported Content-Type \'radom/mime-type\'", \'code\': None}]'
        py3_data = '[{\'message\': "Unsupported Content-Type \'radom/mime-type\'", \'code\': None, \'override\': None}]'
        assert data == py2_data if PY2 else py3_data

        #ATTENTION
        #I would think this should be true
        #assert data == "Unsupported Content-Type 'radom/mime-type'"
        assert status == 415

        kwargs = dict(base_kwargs, **{'method': 'GET', 'headers': {"Content-Type": "application/json", "Accept": "application/xml"}})
        headers, data, status, _ = send_mock_request(**kwargs)
        assert headers["Content-Type"] == "application/xml"
        assert data == try_decode(etree.tostring(etree.fromstring("<errors><error><message>Method not allowed.</message></error></errors>")))
        assert status == 405

        kwargs = dict(base_kwargs, **{'url': 'http://localhost:34567/test/sample_service', 'headers': {"Content-Type": "application/json", "Accept": "application/json"}})
        headers, data, status, _ = send_mock_request(**kwargs)
        assert headers["Content-Type"] == "application/json"
        py2_data = json.dumps({"errors": [{'override': None, 'message': "Not found: \'/test/sample_service\'", 'code': None}]})
        py3_data = '{"errors": [{"message": "Not found: \'/test/sample_service\'", "code": null, "override": null}]}'
        assert data == py2_data if PY2 else py3_data
        assert status == 404

    @create_test_server(outbound_queues=['sample_service'], routes_config={"routes":[{"id": "base","path": "/<queue:re:[a-zA-Z_0-9]+?>","method": ["POST"],"accept_types":["application/json"]}]})
    def test_error_handling_with_atypes(self, base_kwargs, base_resp_kwargs):
        kwargs = dict(base_kwargs, **{'data': '<root>123</root>', 'headers': {"Content-Type": "application/xml", "Accept": "application/xml"}})
        headers, data, status, _ = send_mock_request(**kwargs)
        assert headers["Content-Type"] == "text/html; charset=UTF-8"
        assert status == 406

        kwargs = dict(base_kwargs, **{'data': '<root>123</root>', 'headers': {"Content-Type": "application/xml", "Accept": "application/json"}})
        self._send_timeout_mock_request(**kwargs)
        event = self._get_event(queue_name="sample_service", event_class=XMLHttpEvent)
        headers, data, _, _ = get_mock_response(event=event, **base_resp_kwargs)
        assert headers["Content-Type"] == "application/json"
        assert data == json.dumps({"data":{"root":"123"}})

    @create_test_server(outbound_queues=['sample_service'], routes_config={"routes":[{"id": "base","path": "/<queue:re:[a-zA-Z_0-9]+?>","method": ["POST"],"accept_types":["application/json"]}]}, process_bottle_exceptions=True)
    def test_bottle_error_handling_with_atypes(self, base_kwargs):

        #has route accepts and applies them to content-type header error
        kwargs = dict(base_kwargs, **{'data': '<root>123</root>', 'headers': {"Content-Type": "random/xml", "Accept": "application/json"}})
        headers, data, status, _ = send_mock_request(**kwargs)
        assert headers["Content-Type"] == "application/json"
        assert status == 415
        py2_data = '{"errors": [{"override": null, "message": "Unsupported Content-Type \'random/xml\'", "code": null}]}'
        py3_data = '{"errors": [{"message": "Unsupported Content-Type \'random/xml\'", "code": null, "override": null}]}'
        assert data == py2_data if PY2 else py3_data

        #has route accepts and applies them to accept header error
        kwargs = dict(base_kwargs, **{'data': '<root>123</root>', 'headers': {"Content-Type": "application/xml", "Accept": "application/xml"}})
        headers, data, status, _ = send_mock_request(**kwargs)
        assert headers["Content-Type"] == "application/json"
        assert status == 406
        py2_data = '{"errors": [{"override": null, "message": "Unsupported Accept \'application/xml\'", "code": null}]}'
        py3_data = '{"errors": [{"message": "Unsupported Accept \'application/xml\'", "code": null, "override": null}]}'
        assert data == py2_data if PY2 else py3_data

        #doesn't have route to apply route specific accepts and therefore uses default and requested accepts
        kwargs = dict(base_kwargs, **{'url': 'http://localhost:34567/test/sample_service', 'data': '<root>123</root>', 'headers': {"Content-Type": "application/xml", "Accept": "application/xml"}})
        headers, data, status, _ = send_mock_request(**kwargs)
        assert headers["Content-Type"] == "application/xml"
        assert status == 404
        assert data == "<errors><error><message>Not found: '/test/sample_service'</message></error></errors>"

    @create_test_server(outbound_queues=['sample_service'], inbound_queues=['sample_service'])
    def _test_manual(self):
        routes_config = {"routes":[{"id": "base","path": "/<queue:re:[a-zA-Z_0-9]+?>","method": ["POST"]}]}
        actor = HTTPServer("http_server", port=34567, address="0.0.0.0", routes_config=routes_config)
        actor.pool.outbound.add("sample_service")
        actor.register_consumer("sample_service", actor.pool.outbound["sample_service"])
        actor.start()

        #with self.assertRaises(requests.exceptions.Timeout):
        response = requests.post("http://localhost:34567/sample_service", headers={}, data="some text")
        print(response.text)
        actor.stop()

        resp = send_mock_request(httpserver_actor=self.server_actor, method="POST", url="http://localhost:34567/sample_service?test=123&ok=ok", data="TEST", headers={"Content-Type": "text/plain"})
        print(resp)
