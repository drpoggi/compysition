import unittest

from compysition.actors import EventFilter, EventRouter, EventXMLFilter, EventXMLXpathsFilter
from compysition.errors import QueueEmpty
from compysition.event import Event, XMLEvent
from compysition.testutils.test_actor import _TestActorWrapper

class TestEventRouter(unittest.TestCase):
    timeout = 0.01

    filter_class = EventFilter
    router_class = EventRouter
    event_class = Event

    single_outbox_case = {"value_regexes": "one",
                          "matching_event_kwargs": {"data": "one"},
                          "outbox_names": ["one"]}

    multiple_outbox_case = {"value_regexes": "twothree",
                            "matching_event_kwargs": {"data": "twothree"},
                            "outbox_names": ["two", "three"]}

    regex_match_case = {"value_regexes": "[0-9]{1,10}",
                        "matching_event_kwargs": {"data": "123456"},
                        "outbox_names": ["four"]}

    cases = [single_outbox_case, multiple_outbox_case, regex_match_case]
    DEFAULT_QUEUE = 'default'

    def generate_actor(self, **actor_kwargs):
        filters = list(map(lambda kwargs: self.filter_class(**kwargs), self.cases))
        outbox_queues = [item for sublist in [case['outbox_names'] for case in self.cases] for item in sublist] + [self.DEFAULT_QUEUE]
        actor = self.router_class("eventroutertest", routing_filters=filters, **actor_kwargs)
        return _TestActorWrapper(actor, output_queues=outbox_queues, output_timeout=0.05)

    def setUp(self):
        self.actor = self.generate_actor(type="blacklist")

    def test_data_one_outbox_one_match(self):
        _input = self.event_class(**self.single_outbox_case['matching_event_kwargs'])
        self.actor.input = _input
        for outbox in self.single_outbox_case['outbox_names']:
            _output = self.actor.output_queues[outbox].get(block=True, timeout=self.timeout)
            self.assertIsInstance(_output, Event)

    def test_data_one_outbox_two_mismatch(self):
        _input = self.event_class(**self.single_outbox_case['matching_event_kwargs'])
        mismatching_queue = self.multiple_outbox_case['outbox_names'][0]
        self.actor.input = _input
        with self.assertRaises(QueueEmpty):
            self.actor.output_queues[mismatching_queue].get(block=True, timeout=self.timeout)

    def test_multiple_outboxes_match(self):
        _input = self.event_class(**self.multiple_outbox_case['matching_event_kwargs'])
        self.actor.input = _input
        for outbox in self.multiple_outbox_case['outbox_names']:
            _output = self.actor.output_queues[outbox].get(block=True, timeout=self.timeout)
            self.assertIsInstance(_output, Event)

    def test_complex_regex_match(self):
        _input = self.event_class(**self.regex_match_case['matching_event_kwargs'])
        self.actor.input = _input
        for outbox in self.regex_match_case['outbox_names']:
            _output = self.actor.output_queues[outbox].get(block=True, timeout=self.timeout)
            self.assertIsInstance(_output, Event)

    def test_blacklist_send_to_default_outbox(self):
        _input = self.event_class(data={'foo': 'bar'})
        self.actor.input = _input
        _output = self.actor.output_queues[self.DEFAULT_QUEUE].get(block=True, timeout=self.timeout)
        self.assertIsInstance(_output, Event)

    def test_whitelist_not_sending_to_default(self):
        self.actor = self.generate_actor(type="whitelist")
        _input = self.event_class(data={'foo': 'bar'})
        self.actor.input = _input
        with self.assertRaises(QueueEmpty):
            self.actor.output


class TestEventXMLFilter(TestEventRouter):

    filter_class = EventXMLFilter
    event_class = XMLEvent

    single_outbox_case = {"value_regexes": "one",
                          "xpath": "//foo",
                          "matching_event_kwargs": {"data": "<foo>one</foo>"},
                          "outbox_names": ["one"]}

    multiple_outbox_case = {"value_regexes": "twothree",
                            "xpath": "//foo/bar",
                            "matching_event_kwargs": {"data": "<foo><bar>twothree</bar></foo>"},
                            "outbox_names": ["two", "three"]}

    regex_match_case = {"value_regexes": "[0-9]{1,10}",
                        "xpath": "//foo/@attribute",
                        "matching_event_kwargs": {"data": "<foo attribute='123456' />"},
                        "outbox_names": ["four"]}

    cases = [single_outbox_case, multiple_outbox_case, regex_match_case]


class TestEventXMLXpathsFilter(TestEventRouter):

    filter_class = EventXMLXpathsFilter
    event_class = XMLEvent

    single_outbox_case = {"regex_xpath": "//foo_regex",
                          "xpath": "//foo",
                          "matching_event_kwargs": {"data": "<root><foo>one</foo><foo_regex>one</foo_regex></root>"},
                          "outbox_names": ["one"]}

    multiple_outbox_case = {"regex_xpath": "//bar_regex",
                            "xpath": "//foo/bar",
                            "matching_event_kwargs": {"data": "<foo><bar>twothree</bar><nested><bar_regex>.*twothree.*</bar_regex></nested></foo>"},
                            "outbox_names": ["two", "three"]}

    regex_match_case = {"regex_xpath": "//foo_regex/@regex",
                        "xpath": "//foo/@attribute",
                        "matching_event_kwargs": {"data": "<foo attribute='123456'><foo_regex regex='[0-9]{1,10}'/></foo>"},
                        "outbox_names": ["four"]}

    cases = [single_outbox_case, multiple_outbox_case, regex_match_case]
