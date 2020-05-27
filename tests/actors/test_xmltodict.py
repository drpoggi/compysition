import json
import unittest

from compysition.actors.xml_to_dict import XMLToDict
from compysition.event import XMLEvent
from compysition.testutils.test_actor import _TestActorWrapper

class TestDictToXML(unittest.TestCase):
    """
    Note that this test contains conversion verification tests. This will only occur for actors that explicitly
    change event type as a part of their intended behavior
    """

    def setUp(self):
        self.actor = _TestActorWrapper(XMLToDict("xmltodict"))

    def test_single_root_dict_conversion(self):
        _input = XMLEvent(data="<foo>bar</foo>")
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.data_string(), json.dumps({"foo": "bar"}))

    def test_nested_values_conversion(self):
        _input = XMLEvent(data="<root><foo><foo><bar>barvalue</bar></foo></foo><fubar>barfu</fubar></root>")
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.data_string(), json.dumps({"root": {"foo": {"foo": {"bar": "barvalue"}}, "fubar": "barfu"}}))

    def test_multiple_repeated_elements_conversion(self):
        _input = XMLEvent(data="<root><foo>bar</foo><foo>bar</foo><foo>bar</foo></root>")
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.data_string(), json.dumps({"root": {"foo": ["bar", "bar", "bar"]}}))

    def test_internal_jsonified_conversion(self):
        _input = XMLEvent(data="<jsonified_envelope><errors><foo>bar</foo></errors><errors><foo>bar</foo></errors><errors><foo>bar</foo></errors></jsonified_envelope>")
        self.actor.input = _input
        output = self.actor.output
        self.assertEqual(output.data_string(), json.dumps({"errors": [{"foo": "bar"}, {"foo": "bar"}, {"foo": "bar"}]}))
