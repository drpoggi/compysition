import json
import unittest

from compysition.actors.eventjoin import EventJoin, XMLEventJoin, JSONEventJoin
from compysition.errors import QueueEmpty
from compysition.testutils.test_actor import _TestActorWrapper

class TestEventJoin(unittest.TestCase):

    input_data = "foo"
    output_data = str(["foo", "foo", "foo"])
    actor_class = EventJoin

    def setUp(self):
        self.actor = _TestActorWrapper(self.actor_class("eventjointest"), input_queues=["one", "two", "three"], output_timeout=0.05)

    def test_full_input(self):
        _input = self.actor_class.input(data=self.input_data)
        self.actor.input = _input
        _output = self.actor.output
        self.assertIsInstance(_output, self.actor_class.input)

    def test_two_of_three_input(self):
        _input = self.actor_class.input(data=self.input_data)
        self.actor.input_queues['one'].put(_input)
        self.actor.input_queues['two'].put(_input)
        with self.assertRaises(QueueEmpty):
            self.actor.output

    def test_repeated_single_inbox_input(self):
        _input = self.actor_class.input(data=self.input_data)
        self.actor.input_queues['one'].put(_input)
        self.actor.input_queues['one'].put(_input)
        with self.assertRaises(QueueEmpty):
            self.actor.output

    def test_verify_proper_data_join(self):
        _input = self.actor_class.input(data=self.input_data)
        self.actor.input = _input
        _output = self.actor.output
        self.assertEquals(_output.data_string(), self.output_data)


class TestXMLEventJoin(TestEventJoin):

    input_data = "<foo>bar</foo>"
    output_data = "<eventjointest><foo>bar</foo><foo>bar</foo><foo>bar</foo></eventjointest>"
    actor_class = XMLEventJoin


class TestJSONEventJoin(TestEventJoin):

    input_data = {"foo": "bar"}
    output_data = json.dumps(input_data)
    actor_class = JSONEventJoin
