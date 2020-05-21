import unittest
import json
from lxml import etree
from collections import OrderedDict, Mapping

from compysition.errors import ResourceNotFound, InvalidEventDataModification
from compysition.event import (HttpEvent, Event, CompysitionException, XMLEvent, 
    JSONEvent, JSONHttpEvent, XMLHttpEvent, _XWWWFORMHttpEvent, _XMLXWWWFORMHttpEvent, 
    _JSONXWWWFORMHttpEvent, _XWWWFormList)
from compysition.util import PY2, try_decode

if PY2:
    import urllib
else:
    import urllib.parse as urllib

conversion_classes = [str, etree._Element, etree._ElementTree, etree._XSLTResultTree, dict, list, OrderedDict, None.__class__, _XWWWFormList]

class TestEvent(unittest.TestCase):
    def setUp(self):
        self.event = Event(data={'foo': 'bar'}, meta_id='123456abcdef')

    def test_distinct_meta_and_event_ids(self):
        self.assertNotEqual(self.event.event_id, self.event.meta_id)

class TestHttpEvent(unittest.TestCase):
    def test_default_status(self):
        self.event = HttpEvent(data='quick brown fox')
        self.assertEquals(self.event.status, (200, 'OK'))

    def test_setting_status_tuple(self):
        error = (404, 'Not Found')
        self.event = HttpEvent(data='quick brown fox')
        self.event.status = error
        self.assertEquals(self.event.status, error)

    def test_setting_status_string_space_delimited(self):
        error = '404 Not Found'
        self.event = HttpEvent(data='quick brown fox')
        self.event.status = error
        self.assertEquals(self.event.status, (404, 'Not Found'))

    def test_setting_status_string_dash_delimited(self):
        error = '404-Not Found'
        self.event = HttpEvent(data='quick brown fox')
        self.event.status = error
        self.assertEquals(self.event.status, (404, 'Not Found'))

    def test_resource_not_found_status_updated(self):
        self.event = HttpEvent()
        self.event.error = ResourceNotFound()
        self.assertEquals(self.event.status, (404, 'Not Found'))

    def test_internal_server_error(self):
        self.event = HttpEvent()
        self.event.error = CompysitionException()
        self.assertEquals(self.event.status, (500, 'Internal Server Error'))

    def test_xml_to_json_single_element_default_to_dict(self):
        sample_xml = """
            <root>
                <sample_item>
                    <stuff>45</stuff>
                </sample_item>
            </root>
        """
        event = XMLEvent(data=sample_xml)
        json_event = event.convert(JSONEvent)
        assert isinstance(json_event.data['root']['sample_item'], Mapping)
        assert json_event.data['root']['sample_item']['stuff'] == '45'

    def test_xml_to_json_single_element_should_force_list(self):
        sample_xml = """
            <root>
                <sample_item force_list="True">
                    <stuff>45</stuff>
                </sample_item>
            </root>
        """
        event = XMLEvent(data=sample_xml)
        json_event = event.convert(JSONEvent)
        assert isinstance(json_event.data['root']['sample_item'], list)
        assert json_event.data['root']['sample_item'][0]['stuff'] == '45'

    def test_xml_to_json_multiple_element_default_to_list(self):
        sample_xml = """
            <root>
                <sample_item>
                    <stuff>45</stuff>
                </sample_item>
                <sample_item>
                    <stuff>45</stuff>
                </sample_item>
                <sample_item>
                    <stuff>45</stuff>
                </sample_item>
            </root>
        """
        event = XMLEvent(data=sample_xml)
        json_event = event.convert(JSONEvent)
        assert isinstance(json_event.data['root']['sample_item'], list)
        assert len(json_event.data['root']['sample_item']) == 3

    def test_xml_to_json_multiple_element_should_force_list(self):
        sample_xml = """
            <root>
                <sample_item force_list="True">
                    <stuff>45</stuff>
                </sample_item>
                <sample_item>
                    <stuff>45</stuff>
                </sample_item>
                <sample_item>
                    <stuff>45</stuff>
                </sample_item>
            </root>
        """
        event = XMLEvent(data=sample_xml)
        json_event = event.convert(JSONEvent)
        assert isinstance(json_event.data['root']['sample_item'], list)
        assert json_event.data['root']['sample_item'][2]['stuff'] == '45'
        assert '@force_list' not in json_event.data['root']['sample_item'][0]


    def test_json_to_xml_simple(self):
        sample_json = """
        {"apple": 1}
        """

        e = JSONEvent(data=sample_json)
        xml_event = e.convert(XMLEvent)
        assert xml_event.data_string() == '<apple>1</apple>'

    def test_json_to_xml_to_json_nesting(self):
        sample_json = """
        {"candy": [
            {"apple": 2},
            {"grape": 3}
            ]
        }
        """

        XML_VERSION = ''.join([
        '<jsonified_envelope>',
            '<candy>',
                '<apple>2</apple>',
            '</candy>',
            '<candy>',
                '<grape>3</grape>',
            '</candy>',
        '</jsonified_envelope>',
        ])

        e = JSONEvent(data=sample_json)
        xml_event = e.convert(XMLEvent)
        assert xml_event.data_string() == XML_VERSION

        json_event = xml_event.convert(JSONEvent)
        # check that jsonified_envelope has been removed and data is correct.
        assert 'candy' in json_event.data
        # The type changed from int to str but that's not really avoidable
        assert json_event.data['candy'][0]['apple'] == '2'
        assert json_event.data['candy'][1]['grape'] == '3'


parser = etree.XMLParser(remove_blank_text=True)
#used to ignore spacing differences and look at basic XML structure
def xml_formatter(xml_str):
    return try_decode(etree.tostring(etree.XML(xml_str, parser=parser)))

#used to ignore spacing differences and look at basic JSON structure
def json_formatter(json_str):
    return json.dumps(json.loads(json_str))

class TestXMLEvent(unittest.TestCase):

    event_class = XMLEvent

    string_wrapper = lambda self, data: data

    def test_conversion_classes(self):
        current_conversion_classes = XMLEvent().conversion_methods.keys()
        assert len(current_conversion_classes) == len(conversion_classes)
        for cur_conv_meth in current_conversion_classes:
            assert cur_conv_meth in conversion_classes

    def test_json_conversion_methods(self):
        src = {"my_data":123}
        event = self.event_class(data=src)
        assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<my_data>123</my_data>")
    
        src = {"my_data":{"lvl1":[1,2,3]}}
        event = self.event_class(data=src)
        assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<my_data><lvl1>1</lvl1><lvl1>2</lvl1><lvl1>3</lvl1></my_data>")
        
        src = {"my_data":{"lvl1":1}}
        event = self.event_class(data=src)
        assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<my_data><lvl1>1</lvl1></my_data>")

        src = {"my_data":{"lvl1":1, "@my_attr": "type"}}
        event = self.event_class(data=src)
        assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<my_data my_attr='type'><lvl1>1</lvl1></my_data>")

        src = {"lvl1":[1,2,3]}
        event = self.event_class(data=src)
        assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<jsonified_envelope><lvl1>1</lvl1><lvl1>2</lvl1><lvl1>3</lvl1></jsonified_envelope>")

        src = [1,2,3]
        event = self.event_class(data=src)
        assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<jsonified_envelope><jsonified_envelope>1</jsonified_envelope><jsonified_envelope>2</jsonified_envelope><jsonified_envelope>3</jsonified_envelope></jsonified_envelope>")

        src = {}
        with self.assertRaises(InvalidEventDataModification):
            event = self.event_class(data=src)
        #ATTENTION
        # I think this should be true instead
        #assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<jsonified_envelope/>")

    def test_str_conversion_methods(self):
        src = self.string_wrapper("<my_data my_attr='type'>123</my_data>")
        event = self.event_class(data=src)
        assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<my_data my_attr='type'>123</my_data>")

        src = self.string_wrapper("")
        with self.assertRaises(InvalidEventDataModification):
            event = self.event_class(data=src)
        #ATTENTION
        # I think this should be true instead
        #assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<data/>")
    
        src = self.string_wrapper(json_formatter('{"test":"ok"}'))
        with self.assertRaises(InvalidEventDataModification):
            event = self.event_class(data=src)

        src = self.string_wrapper("some random text")
        with self.assertRaises(InvalidEventDataModification):
            event = self.event_class(data=src)

        src = self.string_wrapper("<element><invalid_xml></element>")
        with self.assertRaises(InvalidEventDataModification):
            event = self.event_class(data=src)

        src = self.string_wrapper("<element>")
        with self.assertRaises(InvalidEventDataModification):
            event = self.event_class(data=src)

    def test_str_conversion_methods_no_wrapper(self):
        src = ""
        with self.assertRaises(InvalidEventDataModification):
            event = self.event_class(data=src)
        #ATTENTION
        # I think this should be true instead
        #assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<data/>")

    def test_none_conversion_methods(self):
        src = None
        event = self.event_class(data=src)
        assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<root/>")
        #ATTENTION
        # I think one of these should be true instead
        #assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<data/>")

    def test_xml_conversion_methods(self):
        src = etree.fromstring(xml_formatter("<my_data my_attr='type'>123</my_data>"))
        event = self.event_class(data=src)
        assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<my_data my_attr='type'>123</my_data>")
    
    def test_xwwwform_conversion_methods(self):
        xwwwform_tests = [
            (_XWWWFormList([{"data": ("123",)}]), "<data>123</data>"),
            (_XWWWFormList([{"data": ("123", "456",)}]), "<x_www_form_envelope><data>123</data><data>456</data></x_www_form_envelope>"),
            (_XWWWFormList([{"data": ('<data type="OT">123</data>',)}]), '<data type="OT">123</data>'),
            (_XWWWFormList([{"data": ("",)}]), "<data/>"),
            (_XWWWFormList([{"data": ("<data>text<element1/></data>",)}]), "<data>text<element1/></data>"),
            (_XWWWFormList([{"data": ("<element1/>text",)}]), "<data><element1/>text</data>"),
            (_XWWWFormList([{"element1": ("",)}, {"element2": ("the",)}]), "<x_www_form_envelope><element1/><element2>the</element2></x_www_form_envelope>"),
            (_XWWWFormList([{"element1": ("ok",)}, {"element2": ("the",)}, {"element1": ("123",)}]), "<x_www_form_envelope><element1>ok</element1><element2>the</element2><element1>123</element1></x_www_form_envelope>"),
            (_XWWWFormList([{"element1": ("ok", '<element1 type="OT"><element3/></element1>')}, {"element2": ("the",)}, {"element1": ("123",)}]), '<x_www_form_envelope><element1>ok</element1><element1 type="OT"><element3/></element1><element2>the</element2><element1>123</element1></x_www_form_envelope>'),
            (_XWWWFormList([]), "<x_www_form_envelope/>")
        ]

        for (src, result) in xwwwform_tests:
            event = self.event_class(data=src)
            assert isinstance(event.data, etree._Element)
            assert try_decode(etree.tostring(event.data)) == result

    def test_data_string(self):
        src = etree.fromstring(xml_formatter("<my_data my_attr='type'>123</my_data>"))
        event = self.event_class(data=src)
        assert event.data_string() == self.string_wrapper(xml_formatter("<my_data my_attr='type'>123</my_data>"))

    def test_error_string(self):
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong")
        assert event.error_string() == self.string_wrapper(xml_formatter("<errors><error><message>Oops Something Went Wrong</message></error></errors>"))
        
        event = self.event_class()
        event.error = InvalidEventDataModification(message=["Oops Something Went Wrong", "Oops Something Else Went Wrong Too"])
        assert event.error_string() == self.string_wrapper(xml_formatter("<errors><error><message>Oops Something Went Wrong</message></error><error><message>Oops Something Else Went Wrong Too</message></error></errors>"))

        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555")
        assert event.error_string() == self.string_wrapper(xml_formatter("<errors><error><message>Oops Something Went Wrong</message><code>555</code></error></errors>"))

        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code=555)
        with self.assertRaises(TypeError):
            event.error_string()
        #ATTENTION
        # I don't think this should throw and error
        # Instead I think this should be true
        #assert event.error_string() == xml_formatter("<errors><error><message>Oops Something Went Wrong</message><code>555</code></error></errors>")

        src = xml_formatter("<my_data my_attr='type'>123</my_data>")
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555", override=src)
        assert event.error_string() == self.string_wrapper(xml_formatter("<my_data my_attr='type'>123</my_data>"))
    
        src = etree.fromstring(xml_formatter("<my_data my_attr='type'>123</my_data>"))
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555", override=src)
        assert event.error_string() == self.string_wrapper(xml_formatter("<errors><error><message>Oops Something Went Wrong</message><code>555</code></error></errors>"))
        #ATTENTION
        # I think this should be true instead
        #assert event.error_string() == self.string_wrapper(xml_formatter("<my_data my_attr='type'>123</my_data>"))

    def test_error_string_edge_case(self):
        src = {"my_data":{"lvl1":1, "@my_attr": "type"}}
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555", override=src)
        assert event.error_string() == {"my_data":{"lvl1":1, "@my_attr": "type"}}
        #ATTENTION
        # I think this should be a string vs a json object
        #assert event.error_string() == json_formatter(json.dumps({"my_data":{"lvl1":1, "@my_attr": "type"}}))

        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555", override="123")
        assert event.error_string() == "123"

class TestJSONEvent(unittest.TestCase):

    event_class = JSONEvent

    string_wrapper = lambda self, data: data

    def test_conversion_classes(self):
        current_conversion_classes = self.event_class.conversion_methods.keys()
        assert len(current_conversion_classes) == len(conversion_classes)
        for cur_conv_meth in current_conversion_classes:
            assert cur_conv_meth in conversion_classes

    def test_json_conversion_methods(self):
        src = {"test":"ok"}
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"test":"ok"}))

        src = {"test":"ok","test2":1234}
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"test":"ok","test2":1234}))

        src = {"test":{"ok":"data"},"test2":[1,2,3,4]}
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"test":{"ok":"data"},"test2":[1,2,3,4]}))

        src = [1,2,3,4]
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps([1,2,3,4]))

        src = {}
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({}))

    def test_xml_conversion_methods(self):
        '''
            Not implemented but a way to translate numbers would be nice
        '''
        
        src = etree.fromstring("<my_data>123</my_data>")
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"my_data":"123"}))

        src = etree.fromstring("<my_data><lvl1>1</lvl1><lvl1>2</lvl1><lvl1>3</lvl1></my_data>")
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"my_data":{"lvl1":["1","2","3"]}}))

        src = etree.fromstring("<my_data><lvl1>1</lvl1></my_data>")
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"my_data":{"lvl1":"1"}}))

        src = etree.fromstring("<my_data my_attr='type'><lvl1>1</lvl1></my_data>")
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data, sort_keys=True)) == json_formatter(json.dumps({"my_data":{"lvl1":"1", "@my_attr": "type"}}, sort_keys=True))

        src = etree.fromstring("<jsonified_envelope><lvl1>1</lvl1><lvl1>2</lvl1><lvl1>3</lvl1></jsonified_envelope>")
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"lvl1":["1","2","3"]}))

        src = etree.fromstring("<jsonified_envelope><jsonified_envelope>1</jsonified_envelope><jsonified_envelope>2</jsonified_envelope><jsonified_envelope>3</jsonified_envelope></jsonified_envelope>")
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"jsonified_envelope":["1","2","3"]}))
        #ATTENTION
        # I think this should be true instead to reverse the functionality of XMLEvent conversion
        #assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps(["1","2","3"]))

        src = etree.fromstring("<jsonified_envelope/>")
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == 'null'
        #ATTENTION
        # I think one of these should be true instead (preferably the first)
        #assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({}))
        #assert event.data == None

        src = etree.fromstring("<my_data force_list=''>123</my_data>")
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"my_data":[{"#text":"123"}]}))
        #ATTENTION
        # I feel like this would be more usable
        #assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"my_data":["123"]}))
        
        src = etree.fromstring("<my_data force_list=''><level1>123</level1></my_data>")
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"my_data":[{"level1":"123"}]}))
        
        src = etree.fromstring("<x_www_form_envelope><lvl1>1</lvl1><lvl1>2</lvl1><lvl1>3</lvl1></x_www_form_envelope>")
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"lvl1":["1","2","3"]}))

    def test_str_conversion_methods(self):
        src = self.string_wrapper(json.dumps({"my_data":"ok"}))
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({"my_data":"ok"}))

        src = self.string_wrapper("")
        with self.assertRaises(InvalidEventDataModification):
            event = self.event_class(data=src)
        #ATTENTION
        # I think this should be true instead
        #assert event.data_string() == json_formatter(json.dumps({}))

        src = self.string_wrapper("some random text")
        with self.assertRaises(InvalidEventDataModification):
            event = self.event_class(data=src)

        src = self.string_wrapper("<some_xml/>")
        with self.assertRaises(InvalidEventDataModification):
            event = self.event_class(data=src)

        src = self.string_wrapper('{"invalid: "json"}')
        with self.assertRaises(InvalidEventDataModification):
            event = self.event_class(data=src)

    def test_str_conversion_methods_no_wrapper(self):
        src = ""
        with self.assertRaises(InvalidEventDataModification):
            event = self.event_class(data=src)
        #ATTENTION
        # I think this should be true instead
        #assert event.data_string() == json_formatter(json.dumps({}))

    def test_none_conversion_methods(self):
        src = None
        event = self.event_class(data=src)
        assert json_formatter(json.dumps(event.data)) == json_formatter(json.dumps({}))

    def test_xwwwform_conversion_methods(self):
        xwwwform_tests = [
            (_XWWWFormList([{"data": ("123",)}]), OrderedDict, json.dumps({"data": 123})),
            (_XWWWFormList([{"data": ("123",)}, {"data2": ("text",)}]), OrderedDict, json.dumps({"data": 123, "data2": "text"})),
            (_XWWWFormList([{"data": ("1","2","3")}]), OrderedDict, json.dumps({"data": [1, 2, 3]})),
            (_XWWWFormList([{"data": (json.dumps({"double":{"nested":"dict"}}),)}]), OrderedDict, json.dumps({"data": {"double":{"nested":"dict"}}})),
            (_XWWWFormList([]), OrderedDict, json.dumps({})),
            (_XWWWFormList([{"jsonified_envelope": ("1", "2", "3")}]), list, json.dumps([1,2,3])),
            (_XWWWFormList([{"test": ("123",)}, {"test2": ("asdf",)}]), OrderedDict, json.dumps({"test": 123, "test2": "asdf"})),
            (_XWWWFormList([{"test": ("123",)}, {"test2": ("asdf",)}, {"test": ("456", "789")}]), list, json.dumps([{"test": [123]}, {"test2": ["asdf"]}, {"test": [456, 789]}])),
            (_XWWWFormList([{"test": ("123",)}, {"test2": (json.dumps({"ok": "more_data"}),)}, {"test": ("456", "789")}]), list, json.dumps([{"test": [123]}, {"test2": [{"ok": "more_data"}]}, {"test": [456, 789]}]))
        ]
        for (src, clazz, result) in xwwwform_tests:
            event = self.event_class(data=src)
            assert isinstance(event.data, clazz)
            assert json.dumps(event.data) == result

    def test_data_string(self):
        src = {"test":"ok"}
        event = self.event_class(data=src)
        assert event.data_string() == self.string_wrapper(json_formatter(json.dumps({"test":"ok"})))

        src = {"test":"ok","test2":1234}
        event = self.event_class(data=src)
        assert event.data_string() == self.string_wrapper(json_formatter(json.dumps({"test":"ok","test2":1234})))

        src = {"test":{"ok":"data"},"test2":[1,2,3,4]}
        event = self.event_class(data=src)
        assert event.data_string() == self.string_wrapper(json_formatter(json.dumps({"test":{"ok":"data"},"test2":[1,2,3,4]})))

        src = [1,2,3,4]
        event = self.event_class(data=src)
        assert event.data_string() == self.string_wrapper(json_formatter(json.dumps([1,2,3,4])))

        src = {}
        event = self.event_class(data=src)
        assert event.data_string() == self.string_wrapper(json_formatter(json.dumps({})))

    def test_error_string(self):
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong")
        assert event.error_string() == self.string_wrapper(json_formatter(json.dumps([{"message":"Oops Something Went Wrong", "code": None, "override":None}])))
        #ATTENTION
        # Probably don't need to return "override" data or null code data        

        event = self.event_class()
        event.error = InvalidEventDataModification(message=["Oops Something Went Wrong", "Oops Something Else Went Wrong Too"])
        assert event.error_string() == self.string_wrapper(json_formatter(json.dumps([{"message":"Oops Something Went Wrong", "code": None, "override":None}, {"message":"Oops Something Else Went Wrong Too", "code": None, "override":None}])))

        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code=555)
        assert event.error_string() == self.string_wrapper(json_formatter(json.dumps([{"message":"Oops Something Went Wrong", "code": 555, "override":None}])))

        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555")
        assert event.error_string() == self.string_wrapper(json_formatter(json.dumps([{"message":"Oops Something Went Wrong", "code": "555", "override":None}])))
        
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555", override="123")
        assert event.error_string() == self.string_wrapper('"123"')
        #ATTENTION
        # This seems odd probably should be without the added quotes
        #assert event.error_string() == self.string_wrapper('123')

        src = {"my_data":123}
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555", override=src)
        assert event.error_string() == self.string_wrapper(json_formatter(json.dumps({"my_data":123})))

    def test_error_string_edge_case(self):
        src = etree.fromstring(xml_formatter("<my_data my_attr='type'>123</my_data>"))
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555", override=src)
        assert isinstance(event.error_string(), list)
        assert isinstance(event.error_string()[0]["override"], etree._Element)
        #ATTENTION
        #This is definitely not right
        #I think it should be
        #assert event.error_string() == etree.tostring(src)

        src = json_formatter(json.dumps({"my_data":123}))
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555", override=src)
        assert event.error_string() == '"{\\\"my_data\\\": 123}"'
        #ATTENTION
        # This seems odd probably should be without the added quotes
        #assert event.error_string() == json_formatter(json.dumps({"my_data":123}))

class TestJSONHttpEvent(TestJSONEvent):

    event_class = JSONHttpEvent

class TestXMLHttpEvent(TestXMLEvent):

    event_class = XMLHttpEvent

class TestXWWWFORMHttpEvent(unittest.TestCase):

    event_class = _XWWWFORMHttpEvent

    def test_conversion_classes(self):
        current_conversion_classes = self.event_class.conversion_methods.keys()
        assert len(current_conversion_classes) == len(conversion_classes)
        for cur_conv_meth in current_conversion_classes:
            assert cur_conv_meth in conversion_classes

    def test_json_conversion_methods(self):
        json_tests = [
            ({"data": 123}, [{"data": ("123",)}]),
            ({"data": 123, "data2": "text"}, [{"data": ("123",)}, {"data2": ("text",)}]),
            ({"data": [1,2,3]}, [{"data": ("1","2","3")}]),
            ({"data": {"double":{"nested":"dict"}}}, [{"data": (json.dumps({"double":{"nested":"dict"}}),)}]),
            ({}, []),
            (OrderedDict(), []),
            ([1,2,3], [{"jsonified_envelope": ("1", "2", "3")}]),
            ([], []),
            ([{"test": 123}, {"test2": "asdf"}], [{"test": ("123",)}, {"test2": ("asdf",)}]),
            ([{"test": [123,]}, {"test2": ["asdf",]}, {"test": (456, 789)}], [{"test": ("123",)}, {"test2": ("asdf",)}, {"test": ("456", "789")}])
        ]

        for (src, result) in json_tests:
            event = self.event_class(data=src)
            assert isinstance(event.data, _XWWWFormList)
            assert event.data == result

    def test_xml_conversion_methods(self):
        xml_tests = [
            (etree.fromstring("<data>123</data>"), [{"data": ("123",)}]),
            (etree.fromstring("<data type='OT'>123</data>"), [{"data": ('<data type="OT">123</data>',)}]),
            (etree.fromstring("<data/>"), [{"data": ("",)}]),
            (etree.fromstring("<data>text<element1/></data>"), [{"data": ("<data>text<element1/></data>",)}]),
            (etree.fromstring("<data><element1/>text</data>"), [{"data": ("<element1/>text",)}]), #apparantly lxml thinks 'text' is part of the 'element1' element
            (etree.fromstring("<x_www_form_envelope><element1/><element2>the</element2></x_www_form_envelope>"), [{"element1": ("",)}, {"element2": ("the",)}]),
            (etree.fromstring("<jsonified_envelope><element1/><element2>the</element2></jsonified_envelope>"), [{"element1": ("",)}, {"element2": ("the",)}]),
            (etree.fromstring("<jsonified_envelope><element1>ok</element1><element2>the</element2><element1>123</element1></jsonified_envelope>"), [{"element1": ("ok",)}, {"element2": ("the",)}, {"element1": ("123",)}]),
            (etree.fromstring("<jsonified_envelope><element1>ok</element1><element1 type='OT'><element3/></element1><element2>the</element2><element1>123</element1></jsonified_envelope>"), [{"element1": ("ok", '<element1 type="OT"><element3/></element1>')}, {"element2": ("the",)}, {"element1": ("123",)}]),
            (etree.fromstring("<jsonified_envelope/>"), []),
            (etree.fromstring("<x_www_form_envelope><data>123</data><data>456</data></x_www_form_envelope>"), [{"data": ("123", "456",)}])
        ]

        for (src, result) in xml_tests:
            event = self.event_class(data=src)
            assert isinstance(event.data, _XWWWFormList)
            assert event.data == result

    def test_str_conversion_methods(self):
        str_tests = [
            ("data=123", [{"data": ("123",)}]),
            ("data=123&data2=text", [{"data": ("123",)}, {"data2": ("text",)}]),
            ("data=1&data=2&data=3", [{"data": ("1","2","3")}]),
            ("data={}".format(urllib.quote(json.dumps({"double":{"nested":"dict"}}), '')), [{"data": (json.dumps({"double":{"nested":"dict"}}),)}]),
            ("", []),
            ("jsonified_envelope=1&jsonified_envelope=2&jsonified_envelope=3", [{"jsonified_envelope": ("1", "2", "3")}]),
            ("test=123&test2=asdf", [{"test": ("123",)}, {"test2": ("asdf",)}]),
            ("test=123&test2=asdf&test=456&test=789", [{"test": ("123",)}, {"test2": ("asdf",)}, {"test": ("456", "789")}]),
            ("data={}".format(urllib.quote('<data type="OT">123</data>', '')), [{"data": ('<data type="OT">123</data>',)}]),
            ("data=", [{"data": ("",)}]),
            ("element1=&element2=the", [{"element1": ("",)}, {"element2": ("the",)}])
        ]

        for (src, result) in str_tests:
            event = self.event_class(data=src)
            assert isinstance(event.data, _XWWWFormList)
            assert event.data == result

    def test_none_conversion_methods(self):
        src = None
        event = self.event_class(data=src)
        assert isinstance(event.data, _XWWWFormList)
        assert event.data == []

    def test_xwwwform_conversion_methods(self):
        src = result = _XWWWFormList([{"data": ("123",)}, {"data2": ("text",)}])
        event = self.event_class(data=src)
        assert isinstance(event.data, _XWWWFormList)
        assert event.data == result

    def test_data_string(self):
        str_tests = [
            (_XWWWFormList([{"data": ("123",)}]), "data=123"),
            (_XWWWFormList([{"data": ("123",)}, {"data2": ("text",)}]), "data=123&data2=text"),
            (_XWWWFormList([{"data": ("1","2","3")}]), "data=1&data=2&data=3"),
            (_XWWWFormList([{"data": (json.dumps({"double":{"nested":"dict"}}),)}]), "data={}".format(urllib.quote(json.dumps({"double":{"nested":"dict"}}), ''))),
            (_XWWWFormList([]), ""),
            (_XWWWFormList([{"jsonified_envelope": ("1", "2", "3")}]), "jsonified_envelope=1&jsonified_envelope=2&jsonified_envelope=3"),
            (_XWWWFormList([{"test": ("123",)}, {"test2": ("asdf",)}]), "test=123&test2=asdf"),
            (_XWWWFormList([{"test": ("123",)}, {"test2": ("asdf",)}, {"test": ("456", "789")}]), "test=123&test2=asdf&test=456&test=789"),
            (_XWWWFormList([{"data": ('<data type="OT">123</data>',)}]), "data={}".format(urllib.quote('<data type="OT">123</data>', ''))),
            (_XWWWFormList([{"data": ("",)}]), "data="),
            (_XWWWFormList([{"element1": ("",)}, {"element2": ("the",)}]), "element1=&element2=the")
        ]

        for (src, result) in str_tests:
            event = self.event_class(data=src)
            assert isinstance(event.data, _XWWWFormList)
            assert event.data_string() == result

    def test_error_string(self):
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong")
        assert event.error_string() == "error=Oops%20Something%20Went%20Wrong"

        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code=123, override="some data")
        assert event.error_string() == "some data"

        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="123", override="some data")
        assert event.error_string() == "some data"

        event = self.event_class()
        event.error = InvalidEventDataModification(message=["Oops Something Went Wrong", "Error2"])
        assert event.error_string() == "error=Oops%20Something%20Went%20Wrong&error=Error2"

class TestXMLXWWWFORMHttpEvent(TestXMLHttpEvent):

    event_class = _XMLXWWWFORMHttpEvent

    string_wrapper = lambda self, data: "XML={}".format(urllib.quote(data, ''))

    def test_str_conversion_methods_no_wrapper(self):
        src = ""
        event = self.event_class(data=src)
        assert xml_formatter(etree.tostring(event.data)) == xml_formatter("<root/>")
        #ATTENTION
        # I think this should be true instead
        #assert etree.tostring(event.data) == xml_formatter("<data/>")

    def test_error_string_edge_case(self):
        src = {"my_data":{"lvl1":1, "@my_attr": "type"}}
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555", override=src)
        assert event.error_string() == src
        #ATTENTION
        # I think this should be a string vs a json object
        #assert event.error_string() == self.string_wrapper(json_formatter(json.dumps(src)))

        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555", override="123")
        assert event.error_string() == "123"

class TestJSONXWWWFORMHttpEvent(TestJSONHttpEvent):

    event_class = _JSONXWWWFORMHttpEvent
    
    string_wrapper = lambda self, data: "JSON={}".format(urllib.quote(data, ''))

    def test_str_conversion_methods_no_wrapper(self):
        src = ""
        event = self.event_class(data=src)
        assert json.dumps(event.data) == json_formatter(json.dumps({}))

    def test_error_string_edge_case(self):
        src = etree.fromstring(xml_formatter("<my_data my_attr='type'>123</my_data>"))
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555", override=src)
        assert isinstance(event.error_string(), list)
        assert isinstance(event.error_string()[0]["override"], etree._Element)
        #ATTENTION
        #This is definitely not right
        #I think it should be
        #assert event.error_string() == etree.tostring(src)

        src = json_formatter(json.dumps({"my_data":123}))
        event = self.event_class()
        event.error = InvalidEventDataModification(message="Oops Something Went Wrong", code="555", override=src)
        assert event.error_string() == self.string_wrapper('"{\\\"my_data\\\": 123}"')
        #ATTENTION
        # This seems odd probably should be without the added quotes
        #assert event.error_string() == self.string_wrapper(json.dumps({"my_data":123}))
