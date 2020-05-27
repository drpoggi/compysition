import unittest

from compysition.actors import EventAttributeModifier, JSONEventAttributeDelete, EventAttributeDelete, EventAttributeRegexSubstitution
from compysition.event import JSONEvent, Event
from compysition.testutils.test_actor import _TestActorWrapper

class TestEventAttributeModifier(unittest.TestCase):
    def test_init(self):
        with self.assertRaises(TypeError):
            actor = EventAttributeModifier()
        actor = EventAttributeModifier('actor')

    def test_defaults(self):
        actor = EventAttributeModifier('actor')
        self.assertEqual('test', 'test')
        self.assertEqual(actor.key, 'data')
        self.assertEqual(actor.log_change, False)
        self.assertEqual(actor.separator, '/')

    def test_get_key_chain_value(self):
        actor1 = EventAttributeModifier(name='actor')
        event = Event()
        event.data = "some test data"
        event = actor1.get_key_chain_value(event, 'new value')
        self.assertEqual(event.data, 'new value')
        event = actor1.get_key_chain_value(event, 'new value')
        ##TODO Continue

class TestJSONEventAttributeDelete(unittest.TestCase):

    def test_single_event_attribute(self):
        actor = _TestActorWrapper(JSONEventAttributeDelete('actor', key_paths=[['foo']]))
        _input = JSONEvent(foo='foo')

        self.assertEqual(_input.foo, 'foo')
        actor.input = _input
        output = actor.output
        with self.assertRaises(AttributeError):
            output.foo

    def test_single_event_attribute_and_data_item(self):
        actor = _TestActorWrapper(JSONEventAttributeDelete('actor', key_paths=[['foo'], ['data', 'bar']]))
        _input = JSONEvent(data={'bar': 'baz'}, foo='foo')

        self.assertEqual(_input.data, {'bar': 'baz'})
        actor.input = _input
        output = actor.output

        self.assertEqual(output.data, {})
        with self.assertRaises(AttributeError):
            output.foo

    def test_nested_data_item(self):
        actor = _TestActorWrapper(JSONEventAttributeDelete('actor', key_paths=[['data', 'fruits', 'apple']]))
        _input = JSONEvent(data={'fruits': {'apple': 1, 'banana': 3}, 'count': 2})

        actor.input = _input
        output = actor.output
        self.assertEqual(output.data, {'count': 2, 'fruits': {'banana': 3}})

class TestEventAttributeDelete(unittest.TestCase):

    def test_single_event_atribute(self):
        actor = _TestActorWrapper(EventAttributeDelete('actor', key_paths=['foo']))
        _input = Event(foo='foo')

        self.assertEqual(_input.foo, 'foo')
        actor.input = _input
        output = actor.output
        with self.assertRaises(AttributeError):
            output.foo

    def test_multiple_event_atribute(self):
        actor = _TestActorWrapper(EventAttributeDelete('actor', key_paths=['foo', 'bar']))
        _input = Event(foo='foo', bar='bar')

        self.assertEqual(_input.foo, 'foo')
        actor.input = _input
        output = actor.output
        with self.assertRaises(AttributeError):
            output.foo

        with self.assertRaises(AttributeError):
            output.bar


class TestEventRegexSubstitution(unittest.TestCase):

    def test_non_data_attribute_substitution(self):
        actor = _TestActorWrapper(EventAttributeRegexSubstitution('actor', pattern='_', event_attr='foo', replace_with=' '))
        _input = Event(foo='the_far_car')

        actor.input = _input
        output = actor.output
        self.assertEquals(output.foo, 'the far car')
