import unittest

from compysition.actors.dicttoxml import DictToXML, PropertiesToXML
from compysition.event import JSONEvent, XMLEvent, XMLHttpEvent, HttpEvent
from compysition.testutils.test_actor import _TestActorWrapper

class TestDictToXML(unittest.TestCase):
    """
    Note that this test contains conversion verification tests. This will only occur for actors that explicitly
    change event type as a part of their intended behavior
    """

    def setUp(self):
        self.actor = _TestActorWrapper(DictToXML("dicttoxml"))

    def test_single_root_dict_conversion(self):
        _input = JSONEvent(data={"foo": "bar"})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.data_string(), "<foo>bar</foo>")

    def test_multiple_root_dict_conversion(self):
        _input = JSONEvent(data={"foo": "bar", "fubar": "barfu"})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.data_string(), "<dicttoxml><foo>bar</foo><fubar>barfu</fubar></dicttoxml>")

    def test_embedded_xml_dict_conversion(self):
        _input = JSONEvent(data={"foo": "<foo><bar>barvalue</bar></foo>", "fubar": "barfu"})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.data_string(), "<dicttoxml><foo><foo><bar>barvalue</bar></foo></foo><fubar>barfu</fubar></dicttoxml>")

    def test_json_event_class_conversion(self):
        _input = JSONEvent(data={"foo": "bar"})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.__class__, XMLEvent)

    def test_http_event_class_conversion(self):
        _input = HttpEvent(data={"foo": "bar"})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.__class__, XMLHttpEvent)

    def test_xml_event_class_consistency(self):
        _input = XMLEvent(data={"foo": "bar"})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.__class__, XMLEvent)
        self.assertEqual(output.data_string(), "<foo>bar</foo>")

    def test_json_list_conversion(self):
        _input = JSONEvent(data={"root": {"foo": ["bar", "bar", "bar"]}})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.data_string(), "<root><foo>bar</foo><foo>bar</foo><foo>bar</foo></root>")

    def test_root_list_conversion(self):
        _input = JSONEvent(data={"errors": [{"foo": "bar"}, {"foo": "bar"}, {"foo": "bar"}]})
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.data_string(), '<jsonified_envelope><errors><foo>bar</foo></errors><errors><foo>bar</foo></errors><errors><foo>bar</foo></errors></jsonified_envelope>')


class TestPropertiesToXML(unittest.TestCase):

    def setUp(self):
        self.actor = _TestActorWrapper(PropertiesToXML("propertiestoxml"))

    def test_event_property_xml_conversion(self):
        _input = XMLEvent(data={"foo": "bar"})
        self.actor.input = _input
        output = self.actor.output
        self.assertRegexpMatches(output.data_string(), "<propertiestoxml>.*<service>.*<\/service>.*<\/propertiestoxml>")
