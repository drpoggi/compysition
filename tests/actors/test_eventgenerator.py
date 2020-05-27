import unittest
import gevent
import time
import math

from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.schedulers.gevent import GeventScheduler

from compysition.actors.eventgenerator import (
    EventGenerator, UDPEventGenerator, CronEventGenerator, UDPCronEventGenerator, 
    EventProducer, UDPEventProducer, ScheduledEventProducer, ScheduledUDPEventProducer,
    CallbackEventProducer, CallbackScheduledEventProducer, IntervalSchedulingMixin,
    CronSchedulingMixin, EventGenerator, CallbackEventGenerator, UDPEventGenerator,
    CronEventGenerator, UDPCronEventGenerator)
from compysition.event import Event, XMLEvent, JSONEvent
from compysition.testutils.test_actor import _TestActorWrapper

class MockedPeersInterface():
    def __init__(self, is_master=False):
        self._is_master = is_master
        self.is_running = False

    def start(self):
        self.is_running = True

    def is_master(self):
        return self._is_master

class MockedScheduler():
    def __init__(self, is_master=False):
        self.is_running = False
        self.job_count = 0

    def start(self):
        self.is_running = True

    def shutdown(self):
        self.is_running = False

    def add_job(self, *args, **kwargs):
        self.job_count += 1


class MockedSchedulingMixin():
    DEFAULT_INTERVAL = {"test_interval": 0}

    def _parse_interval(self, interval):
        self.parsed = True
        return interval

    def _initialize_jobs(self):
        self.jobs_initialized = True

class MockedActorMixin:
    parsed = False
    jobs_initialized = False

class PrepClazz:
    def actor_prep(self, actor, *args, **kwargs):
        self.sent_event = None
        self.errored_event = None
        actor.send_event = self.mock_send_event
        actor.send_error = self.mock_error_event
        actor.output = (actor.output, ) #performed during Base Actor start()
        return actor

    def mock_send_event(self, event, *args, **kwargs):
        self.sent_event = event

    def mock_error_event(self, event, *args, **kwargs):
        self.errored_event = event

    def mock_do_produce(self):
        self.mock_data = self.mock_data + 1

    def produce_event_class_testing_template(self, event_class=None, *args, **kwargs):
        actor = self.__test_class__('actor', *args, **kwargs)
        if event_class:
            actor = self.__test_class__('actor', event_class=event_class, *args, **kwargs)
        else:
            event_class = Event
        self.assertEqual(actor.output, event_class)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertIsInstance(self.sent_event, event_class)

class MockedSchedulingActor(PrepClazz):
    def __init__(self, name, producers=1, interval=5, delay=0, scheduler=None, *args, **kwargs):
        self.interval = self._parse_interval(interval)
        self.delay = delay
        self.producers = producers
        self.scheduler = scheduler
        if not self.scheduler:
            self.scheduler = GeventScheduler()

    def _do_produce(self):
        self.mock_do_produce()

    def pre_hook(self):
        self.scheduler.start()

class TestEventProducer(unittest.TestCase, PrepClazz):
    class MockedEventProducer(MockedActorMixin, EventProducer):
        pass

    __test_class__ = MockedEventProducer

    def test_init(self, *args, **kwargs):
        actor = self.__test_class__('actor', *args, **kwargs)
        self.assertEqual(actor.generate_error, False)
        self.assertEqual(actor.event_kwargs, {})
        self.assertEqual(actor.output, Event)

    def test_do_produce(self, *args, **kwargs):
        #tests event class generation
        self.produce_event_class_testing_template(*args, **kwargs)
        self.produce_event_class_testing_template(event_class=Event, *args, **kwargs)
        self.produce_event_class_testing_template(event_class=XMLEvent, *args, **kwargs)
        self.produce_event_class_testing_template(event_class=JSONEvent, *args, **kwargs)

        #tests error handling
        actor = self.__test_class__('actor', *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertIsInstance(self.sent_event, Event)
        self.assertEqual(self.errored_event, None)
        actor = self.__test_class__('actor', generate_error=False, *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertIsInstance(self.sent_event, Event)
        self.assertEqual(self.errored_event, None)
        actor = self.__test_class__('actor', generate_error=True, *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertIsInstance(self.sent_event, Event)
        self.assertIsInstance(self.errored_event, Event)

        #tests kwargs
        actor = self.__test_class__('actor', event_kwargs={'test_data': 'some_value'}, *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertEqual(self.sent_event.get('test_data', None), 'some_value')
        actor = self.__test_class__('actor', *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertEqual(self.sent_event.get('test_data', None), None)

    def test_consume(self, *args, **kwargs):
        self.test_do_produce()

class TestUDPEventProducer(TestEventProducer):
    class MockedUDPEventProducer(MockedActorMixin, UDPEventProducer):
        pass

    __test_class__ = MockedUDPEventProducer

    def test_init(self, *args, **kwargs):
        actor = self.__test_class__('actor', peers_interface=MockedPeersInterface(), *args, **kwargs)

    def test_pre_hook(self, *args, **kwargs):
        actor = self.__test_class__('actor', peers_interface=MockedPeersInterface(), *args, **kwargs)
        actor.pre_hook()
        self.assertTrue(actor.peers_interface.is_running)

    def test_do_produce(self, *args, **kwargs):        
        actor = self.__test_class__('actor', interval=1, peers_interface=MockedPeersInterface(is_master=False), *args, **kwargs)
        actor = self.actor_prep(actor)
        self.assertFalse(actor.peers_interface.is_master())
        self.assertEqual(getattr(self, 'sent_event', None), None)
        actor._do_produce()
        self.assertEqual(getattr(self, 'sent_event', None), None)

        actor = self.__test_class__('actor', peers_interface=MockedPeersInterface(is_master=True), *args, **kwargs)
        actor = self.actor_prep(actor)
        self.assertTrue(actor.peers_interface.is_master())
        self.assertEqual(getattr(self, 'sent_event', None), None)
        actor._do_produce()
        self.assertIsInstance(getattr(self, 'sent_event', None), Event)

        #this complexity requires __test_class__
        TestEventProducer.test_do_produce(self, peers_interface=MockedPeersInterface(is_master=True), *args, **kwargs)

class TestScheduledEventProducer(TestEventProducer):
    class MockedScheduledEventProducer(MockedActorMixin, MockedSchedulingMixin, ScheduledEventProducer):
        pass

    __test_class__ = MockedScheduledEventProducer

    def test_init(self, *args, **kwargs):
        TestEventProducer.test_init(self, *args, **kwargs)

        actor = self.__test_class__('actor', *args, **kwargs)
        self.assertEqual(actor.interval, 5)
        self.assertEqual(actor.delay, 0)
        self.assertEqual(actor.producers, 1)
        self.assertNotEqual(actor.scheduler, None)
        self.assertEqual(actor.parsed, True)
        self.assertEqual(actor.interval_grace_time, None)

class MockedPeersInterface():
    def __init__(self, is_master=False):
        self._is_master = is_master
        self.is_running = False

    def start(self):
        self.is_running = True

    def is_master(self):
        return self._is_master

class MockedScheduler():
    def __init__(self, is_master=False):
        self.is_running = False
        self.job_count = 0

    def start(self):
        self.is_running = True

    def shutdown(self):
        self.is_running = False

    def add_job(self, *args, **kwargs):
        self.job_count += 1


class MockedSchedulingMixin():
    DEFAULT_INTERVAL = {"test_interval": 0}

    def _parse_interval(self, interval):
        self.parsed = True
        return interval

    def _initialize_jobs(self):
        self.jobs_initialized = True

class MockedActorMixin:
    parsed = False
    jobs_initialized = False

class PrepClazz:
    def actor_prep(self, actor, *args, **kwargs):
        self.sent_event = None
        self.errored_event = None
        actor.send_event = self.mock_send_event
        actor.send_error = self.mock_error_event
        actor.output = (actor.output, ) #performed during Base Actor start()
        return actor

    def mock_send_event(self, event, *args, **kwargs):
        self.sent_event = event

    def mock_error_event(self, event, *args, **kwargs):
        self.errored_event = event

    def mock_do_produce(self):
        self.mock_data = self.mock_data + 1

    def produce_event_class_testing_template(self, event_class=None, *args, **kwargs):
        actor = self.__test_class__('actor', *args, **kwargs)
        if event_class:
            actor = self.__test_class__('actor', event_class=event_class, *args, **kwargs)
        else:
            event_class = Event
        self.assertEqual(actor.output, event_class)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertIsInstance(self.sent_event, event_class)

class MockedSchedulingActor(PrepClazz):
    def __init__(self, name, producers=1, interval=5, delay=0, scheduler=None, *args, **kwargs):
        self.interval = self._parse_interval(interval)
        self.delay = delay
        self.producers = producers
        self.scheduler = scheduler
        if not self.scheduler:
            self.scheduler = GeventScheduler()

    def _do_produce(self):
        self.mock_do_produce()

    def pre_hook(self):
        self.scheduler.start()

class TestEventProducer(unittest.TestCase, PrepClazz):
    class MockedEventProducer(MockedActorMixin, EventProducer):
        pass

    __test_class__ = MockedEventProducer

    def test_init(self, *args, **kwargs):
        actor = self.__test_class__('actor', *args, **kwargs)
        self.assertEqual(actor.generate_error, False)
        self.assertEqual(actor.event_kwargs, {})
        self.assertEqual(actor.output, Event)

    def test_do_produce(self, *args, **kwargs):
        #tests event class generation
        self.produce_event_class_testing_template(*args, **kwargs)
        self.produce_event_class_testing_template(event_class=Event, *args, **kwargs)
        self.produce_event_class_testing_template(event_class=XMLEvent, *args, **kwargs)
        self.produce_event_class_testing_template(event_class=JSONEvent, *args, **kwargs)

        #tests error handling
        actor = self.__test_class__('actor', *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertIsInstance(self.sent_event, Event)
        self.assertEqual(self.errored_event, None)
        actor = self.__test_class__('actor', generate_error=False, *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertIsInstance(self.sent_event, Event)
        self.assertEqual(self.errored_event, None)
        actor = self.__test_class__('actor', generate_error=True, *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertIsInstance(self.sent_event, Event)
        self.assertIsInstance(self.errored_event, Event)

        #tests kwargs
        actor = self.__test_class__('actor', event_kwargs={'test_data': 'some_value'}, *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertEqual(self.sent_event.get('test_data', None), 'some_value')
        actor = self.__test_class__('actor', *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertEqual(self.sent_event.get('test_data', None), None)

    def test_consume(self, *args, **kwargs):
        self.test_do_produce()

class TestUDPEventProducer(TestEventProducer):
    class MockedUDPEventProducer(MockedActorMixin, UDPEventProducer):
        pass

    __test_class__ = MockedUDPEventProducer

    def test_init(self, *args, **kwargs):
        actor = self.__test_class__('actor', peers_interface=MockedPeersInterface(), *args, **kwargs)

    def test_pre_hook(self, *args, **kwargs):
        actor = self.__test_class__('actor', peers_interface=MockedPeersInterface(), *args, **kwargs)
        actor.pre_hook()
        self.assertTrue(actor.peers_interface.is_running)

    def test_do_produce(self, *args, **kwargs):        
        actor = self.__test_class__('actor', interval=1, peers_interface=MockedPeersInterface(is_master=False), *args, **kwargs)
        actor = self.actor_prep(actor)
        self.assertFalse(actor.peers_interface.is_master())
        self.assertEqual(getattr(self, 'sent_event', None), None)
        actor._do_produce()
        self.assertEqual(getattr(self, 'sent_event', None), None)

        actor = self.__test_class__('actor', peers_interface=MockedPeersInterface(is_master=True), *args, **kwargs)
        actor = self.actor_prep(actor)
        self.assertTrue(actor.peers_interface.is_master())
        self.assertEqual(getattr(self, 'sent_event', None), None)
        actor._do_produce()
        self.assertIsInstance(getattr(self, 'sent_event', None), Event)

        #this complexity requires __test_class__
        TestEventProducer.test_do_produce(self, peers_interface=MockedPeersInterface(is_master=True), *args, **kwargs)

class TestScheduledEventProducer(TestEventProducer):
    class MockedScheduledEventProducer(MockedActorMixin, MockedSchedulingMixin, ScheduledEventProducer):
        pass

    __test_class__ = MockedScheduledEventProducer

    def test_init(self, *args, **kwargs):
        TestEventProducer.test_init(self, *args, **kwargs)

        actor = self.__test_class__('actor', *args, **kwargs)
        self.assertEqual(actor.interval, 5)
        self.assertEqual(actor.delay, 0)
        self.assertEqual(actor.producers, 1)
        self.assertNotEqual(actor.scheduler, None)
        self.assertEqual(actor.parsed, True)

class MockedPeersInterface():
    def __init__(self, is_master=False):
        self._is_master = is_master
        self.is_running = False

    def start(self):
        self.is_running = True

    def is_master(self):
        return self._is_master

class MockedScheduler():
    def __init__(self, is_master=False):
        self.is_running = False
        self.job_count = 0

    def start(self):
        self.is_running = True

    def shutdown(self):
        self.is_running = False

    def add_job(self, *args, **kwargs):
        self.job_count += 1


class MockedSchedulingMixin():
    DEFAULT_INTERVAL = {"test_interval": 0}

    def _parse_interval(self, interval):
        self.parsed = True
        return interval

    def _initialize_jobs(self):
        self.jobs_initialized = True

class MockedActorMixin:
    parsed = False
    jobs_initialized = False

class PrepClazz:
    def actor_prep(self, actor, *args, **kwargs):
        self.sent_event = None
        self.errored_event = None
        actor.send_event = self.mock_send_event
        actor.send_error = self.mock_error_event
        actor.output = (actor.output, ) #performed during Base Actor start()
        return actor

    def mock_send_event(self, event, *args, **kwargs):
        self.sent_event = event

    def mock_error_event(self, event, *args, **kwargs):
        self.errored_event = event

    def mock_do_produce(self):
        self.mock_data = self.mock_data + 1

    def produce_event_class_testing_template(self, event_class=None, *args, **kwargs):
        actor = self.__test_class__('actor', *args, **kwargs)
        if event_class:
            actor = self.__test_class__('actor', event_class=event_class, *args, **kwargs)
        else:
            event_class = Event
        self.assertEqual(actor.output, event_class)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertIsInstance(self.sent_event, event_class)

class MockedSchedulingActor(PrepClazz):
    def __init__(self, name, producers=1, interval=5, delay=0, scheduler=None, *args, **kwargs):
        self.interval = self._parse_interval(interval)
        self.delay = delay
        self.producers = producers
        self.scheduler = scheduler
        if not self.scheduler:
            self.scheduler = GeventScheduler()

    def _do_produce(self):
        self.mock_do_produce()

    def pre_hook(self):
        self.scheduler.start()

class TestEventProducer(unittest.TestCase, PrepClazz):
    class MockedEventProducer(MockedActorMixin, EventProducer):
        pass

    __test_class__ = MockedEventProducer

    def test_init(self, *args, **kwargs):
        actor = self.__test_class__('actor', *args, **kwargs)
        self.assertEqual(actor.generate_error, False)
        self.assertEqual(actor.event_kwargs, {})
        self.assertEqual(actor.output, Event)

    def test_do_produce(self, *args, **kwargs):
        #tests event class generation
        self.produce_event_class_testing_template(*args, **kwargs)
        self.produce_event_class_testing_template(event_class=Event, *args, **kwargs)
        self.produce_event_class_testing_template(event_class=XMLEvent, *args, **kwargs)
        self.produce_event_class_testing_template(event_class=JSONEvent, *args, **kwargs)

        #tests error handling
        actor = self.__test_class__('actor', *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertIsInstance(self.sent_event, Event)
        self.assertEqual(self.errored_event, None)
        actor = self.__test_class__('actor', generate_error=False, *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertIsInstance(self.sent_event, Event)
        self.assertEqual(self.errored_event, None)
        actor = self.__test_class__('actor', generate_error=True, *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertIsInstance(self.sent_event, Event)
        self.assertIsInstance(self.errored_event, Event)

        #tests kwargs
        actor = self.__test_class__('actor', event_kwargs={'test_data': 'some_value'}, *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertEqual(self.sent_event.get('test_data', None), 'some_value')
        actor = self.__test_class__('actor', *args, **kwargs)
        actor = self.actor_prep(actor)
        actor._do_produce()
        self.assertEqual(self.sent_event.get('test_data', None), None)

    def test_consume(self, *args, **kwargs):
        self.test_do_produce()

class TestUDPEventProducer(TestEventProducer):
    class MockedUDPEventProducer(MockedActorMixin, UDPEventProducer):
        pass

    __test_class__ = MockedUDPEventProducer

    def test_init(self, *args, **kwargs):
        actor = self.__test_class__('actor', peers_interface=MockedPeersInterface(), *args, **kwargs)

    def test_pre_hook(self, *args, **kwargs):
        actor = self.__test_class__('actor', peers_interface=MockedPeersInterface(), *args, **kwargs)
        actor.pre_hook()
        self.assertTrue(actor.peers_interface.is_running)

    def test_do_produce(self, *args, **kwargs):        
        actor = self.__test_class__('actor', interval=1, peers_interface=MockedPeersInterface(is_master=False), *args, **kwargs)
        actor = self.actor_prep(actor)
        self.assertFalse(actor.peers_interface.is_master())
        self.assertEqual(getattr(self, 'sent_event', None), None)
        actor._do_produce()
        self.assertEqual(getattr(self, 'sent_event', None), None)

        actor = self.__test_class__('actor', peers_interface=MockedPeersInterface(is_master=True), *args, **kwargs)
        actor = self.actor_prep(actor)
        self.assertTrue(actor.peers_interface.is_master())
        self.assertEqual(getattr(self, 'sent_event', None), None)
        actor._do_produce()
        self.assertIsInstance(getattr(self, 'sent_event', None), Event)

        #this complexity requires __test_class__
        TestEventProducer.test_do_produce(self, peers_interface=MockedPeersInterface(is_master=True), *args, **kwargs)

class TestScheduledEventProducer(TestEventProducer):
    class MockedScheduledEventProducer(MockedActorMixin, MockedSchedulingMixin, ScheduledEventProducer):
        pass

    __test_class__ = MockedScheduledEventProducer

    def test_init(self, *args, **kwargs):
        TestEventProducer.test_init(self, *args, **kwargs)

        actor = self.__test_class__('actor', *args, **kwargs)
        self.assertEqual(actor.interval, 5)
        self.assertEqual(actor.delay, 0)
        self.assertEqual(actor.producers, 1)
        self.assertNotEqual(actor.scheduler, None)
        self.assertEqual(actor.parsed, True)

        actor = self.__test_class__('actor', interval=2, delay=3, producers=4, *args, **kwargs)
        self.assertEqual(actor.interval, 2)
        self.assertEqual(actor.delay, 3)
        self.assertEqual(actor.producers, 4)
        self.assertNotEqual(actor.scheduler, None)

    def test_pre_hook(self, *args, **kwargs):
        #test jobs initialization
        actor = self.__test_class__('actor', scheduler=MockedScheduler(), *args, **kwargs)
        self.assertEqual(actor.jobs_initialized, False)
        actor.pre_hook()
        self.assertEqual(actor.jobs_initialized, True)

        #test delay
        actor = self.__test_class__('actor', delay=2, scheduler=MockedScheduler(), *args, **kwargs)
        start = time.time()
        actor.pre_hook()
        end = time.time()
        dif = end - start
        self.assertGreater(dif, 1)
        self.assertGreater(3, dif)

        #test scheduler start
        actor = self.__test_class__('actor', scheduler=MockedScheduler(), *args, **kwargs)
        self.assertEqual(actor.scheduler.is_running, False)
        actor.pre_hook()
        self.assertEqual(actor.scheduler.is_running, True)

    def test_post_hook(self, *args, **kwargs):
        actor = self.__test_class__('actor', scheduler=MockedScheduler(), *args, **kwargs)
        actor.scheduler.is_running = True
        actor.post_hook()
        self.assertEqual(actor.scheduler.is_running, False)

class TestScheduledUDPEventProducer(TestUDPEventProducer, TestScheduledEventProducer):
    class MockedScheduledUDPEventProducer (MockedActorMixin, MockedSchedulingMixin, ScheduledUDPEventProducer):
        pass

    __test_class__ = MockedScheduledUDPEventProducer

    def test_init(self, *args, **kwargs):
        #this complexity requires __test_class__
        TestUDPEventProducer.test_init(self, *args, **kwargs)
        TestScheduledEventProducer.test_init(self, peers_interface=MockedPeersInterface(), *args, **kwargs)

    def test_post_hook(self, *args, **kwargs):
        super(TestScheduledUDPEventProducer, self).test_post_hook(peers_interface=MockedPeersInterface(), *args, **kwargs)

    def test_pre_hook(self, *args, **kwargs):
        #this complexity requires __test_class__
        TestScheduledEventProducer.test_pre_hook(self, peers_interface=MockedPeersInterface(), *args, **kwargs)
        TestUDPEventProducer.test_pre_hook(self, scheduler=MockedScheduler(), *args, **kwargs)

class TestCallbackEventProducer(TestEventProducer):
    class MockedCallbackEventProducer(MockedActorMixin, CallbackEventProducer):
        pass

    __test_class__ = MockedCallbackEventProducer

    def test_init(self, *args, **kwargs):
        TestEventProducer.test_init(self, *args, **kwargs)
        actor = self.__test_class__('actor', *args, **kwargs)
        self.assertEqual(actor.is_running, False)
        actor = self.__test_class__('actor', is_running=True, *args, **kwargs)
        self.assertEqual(actor.is_running, True)

    def test_do_produce(self, *args, **kwargs):
        actor = self.__test_class__('actor', *args, **kwargs)
        actor = self.actor_prep(actor)
        self.assertEqual(actor.is_running, False)
        actor._do_produce()
        self.assertEqual(actor.is_running, True)

        actor = self.__test_class__('actor', is_running=True, *args, **kwargs)
        actor = self.actor_prep(actor)
        self.assertEqual(actor.is_running, True)
        actor._do_produce()
        self.assertEqual(actor.is_running, True)
 
        TestEventProducer.test_do_produce(self)
        try:
            TestEventProducer.test_do_produce(self, is_running=True) #this should fail, hence try block
            self.assertTrue(False)
        except AssertionError:
            self.assertTrue(True)

    def test_consume(self, *args, **kwargs):
        actor = self.__test_class__('actor', *args, **kwargs)
        self.assertEqual(actor.is_running, False)
        actor.consume(event=None)
        self.assertEqual(actor.is_running, False)

        actor = self.__test_class__('actor', is_running=True, *args, **kwargs)
        self.assertEqual(actor.is_running, True)
        actor.consume(event=None)
        self.assertEqual(actor.is_running, False)

class TestCallbackScheduledEventProducer(TestCallbackEventProducer, TestScheduledEventProducer):
    class MockedCallbackScheduledEventProducer(MockedActorMixin, MockedSchedulingMixin, CallbackScheduledEventProducer):
        pass

    __test_class__ = MockedCallbackScheduledEventProducer

    def test_init(self, *args, **kwargs):
        actor = self.__test_class__('actor', scheduler=MockedScheduler(), *args, **kwargs)
        TestCallbackEventProducer.test_init(self, scheduler=MockedScheduler(), *args, **kwargs)
        TestScheduledEventProducer.test_init(self)

class TestIntervalSchedulingMixin(unittest.TestCase):
    class MockedIntervalSchedulingActor(MockedActorMixin, IntervalSchedulingMixin, MockedSchedulingActor):
        pass

    __test_class__ = MockedIntervalSchedulingActor

    def test_init(self, *args, **kwargs):
        actor = self.__test_class__('actor', *args, **kwargs)
        self.assertEqual(actor.DEFAULT_INTERVAL, {'weeks': 0,'days': 0,'hours': 0,'minutes': 0,'seconds': 5})

    def test_parse_interval(self, *args, **kwargs):
        actor = self.__test_class__('actor', *args, **kwargs)
        self.assertEqual(actor._parse_interval(10), {'weeks': 0,'days': 0,'hours': 0,'minutes': 0,'seconds': 10})
        self.assertEqual(actor._parse_interval({'something else': 10}), {'weeks': 0,'days': 0,'hours': 0,'minutes': 0,'seconds': 5})
        self.assertEqual(actor._parse_interval({'days': 10}), {'weeks': 0,'days': 10,'hours': 0,'minutes': 0,'seconds': 5})
        self.assertEqual(actor._parse_interval([1,2,3]), {'weeks': 0,'days': 0,'hours': 0,'minutes': 0,'seconds': 5})
        self.assertEqual(actor._parse_interval('test'), {'weeks': 0,'days': 0,'hours': 0,'minutes': 0,'seconds': 5})

    def test_initialize_jobs(self, *args, **kwargs):
        actor = self.__test_class__('actor', producers=1, *args, **kwargs)
        self.assertEqual(len(actor.scheduler.get_jobs()), 0)
        actor._initialize_jobs()
        self.assertEqual(len(actor.scheduler.get_jobs()), 1)
        actor = self.__test_class__('actor', producers=3, *args, **kwargs)
        self.assertEqual(len(actor.scheduler.get_jobs()), 0)
        actor._initialize_jobs()
        jobs = actor.scheduler.get_jobs()
        self.assertEqual(len(jobs), 3)
        self.assertEqual(jobs[0].func, actor._do_produce)
        self.assertIsInstance(jobs[0].trigger, IntervalTrigger)

class TestInveralScheduling(unittest.TestCase, PrepClazz):
    class MockedIntervalSchedulingProducer(MockedActorMixin, IntervalSchedulingMixin, ScheduledEventProducer):
        pass

    __test_class__ = MockedIntervalSchedulingProducer

    def test_interval_scheduling(self, *args, **kwargs):
        actor = self.__test_class__('actor', delay=0, interval=2, *args, **kwargs)
        self.mock_data = 0
        actor._do_produce = self.mock_do_produce
        actor.pre_hook()
        #actor.scheduler.start()
        
        #tests interval
        self.assertEqual(self.mock_data, 0)
        gevent.sleep(1)
        self.assertEqual(self.mock_data, 0)
        gevent.sleep(2)
        self.assertEqual(self.mock_data, 1)
        gevent.sleep(2)
        self.assertEqual(self.mock_data, 2)

        #tests stopping
        actor.post_hook()
        gevent.sleep(2)
        self.assertEqual(self.mock_data, 2)

class TestCronSchedulingMixin(unittest.TestCase):
    class MockedCronSchedulingActor(MockedActorMixin, CronSchedulingMixin, MockedSchedulingActor):
        pass

    __test_class__ = MockedCronSchedulingActor

    def test_init(self, *args, **kwargs):
        actor = self.__test_class__('actor', scheduler="something trivial", *args, **kwargs)
        self.assertEqual(actor.DEFAULT_INTERVAL, {'year': '*','month': '*','day': '*','week': '*','day_of_week': '*','hour': '*','minute': '*','second': '*/12'})

    def test_parse_interval(self, *args, **kwargs):
        actor = self.__test_class__('actor', scheduler="something trivial", *args, **kwargs)
        self.assertEqual(actor._parse_interval(10), {'year': '*','month': '*','day': '*','week': '*','day_of_week': '*','hour': '*','minute': '*','second': '*/12'})
        self.assertEqual(actor._parse_interval({'something else': 10}), {'year': '*','month': '*','day': '*','week': '*','day_of_week': '*','hour': '*','minute': '*','second': '*/12'})
        self.assertEqual(actor._parse_interval({'day': 10}), {'year': '*','month': '*','day': '10','week': '*','day_of_week': '*','hour': '*','minute': '*','second': '*/12'})
        self.assertEqual(actor._parse_interval({'day': '10'}), {'year': '*','month': '*','day': '10','week': '*','day_of_week': '*','hour': '*','minute': '*','second': '*/12'})
        self.assertEqual(actor._parse_interval([1,2,3]), {'year': '*','month': '*','day': '*','week': '*','day_of_week': '*','hour': '*','minute': '*','second': '*/12'})
        self.assertEqual(actor._parse_interval('test'), {'year': '*','month': '*','day': '*','week': '*','day_of_week': '*','hour': '*','minute': '*','second': '*/12'})

    def test_initialize_jobs(self, *args, **kwargs):
        actor = CronEventGenerator('actor', producers=1)
        self.assertEqual(len(actor.scheduler.get_jobs()), 0)
        actor._initialize_jobs()
        self.assertEqual(len(actor.scheduler.get_jobs()), 1)
        actor = CronEventGenerator('actor', producers=3)
        self.assertEqual(len(actor.scheduler.get_jobs()), 0)
        actor._initialize_jobs()
        jobs = actor.scheduler.get_jobs()
        self.assertEqual(len(jobs), 3)
        self.assertEqual(jobs[0].func, actor._do_produce)
        self.assertIsInstance(jobs[0].trigger, CronTrigger)

class TestCronScheduling(unittest.TestCase, PrepClazz):
    class MockedCronSchedulingProducer(MockedActorMixin, CronSchedulingMixin, ScheduledEventProducer):
        pass

    __test_class__ = MockedCronSchedulingProducer

    def test_cron_scheduling(self, *args, **kwargs):
        actor = self.__test_class__('actor', delay=0, interval={'second': '*/2'}, *args, **kwargs)
        self.mock_data = 0
        actor._do_produce = self.mock_do_produce
        now = time.time()
        if math.floor(now) % 2 == 1:
            gevent.sleep(1)
        actor.pre_hook()
        
        #tests cron
        self.assertEqual(self.mock_data, 0)
        gevent.sleep(1)
        self.assertEqual(self.mock_data, 0)
        gevent.sleep(2)
        self.assertEqual(self.mock_data, 1)
        gevent.sleep(2)
        self.assertEqual(self.mock_data, 2)

        #tests stopping
        actor.post_hook()
        gevent.sleep(2)
        self.assertEqual(self.mock_data, 2)
       
class TestEventGenerator(unittest.TestCase):
    __test_class__ = EventGenerator

    def test_inheritance(self):
        self.assertEqual(len(self.__test_class__.__bases__), 2)
        self.assertEqual(self.__test_class__.__bases__[0], IntervalSchedulingMixin)
        self.assertEqual(self.__test_class__.__bases__[1], ScheduledEventProducer)

    def test_xmlevent_generation(self, *args, **kwargs):
        actor = _TestActorWrapper(self.__test_class__("eventgenerator", interval=1, delay=0, event_class=XMLEvent))
        _output = actor.output
        self.assertIsInstance(_output, XMLEvent)

    def test_event_generation(self, *args, **kwargs):
        actor = _TestActorWrapper(self.__test_class__("eventgenerator", interval=1, delay=0, event_class=Event))
        _output = actor.output
        self.assertIsInstance(_output, Event)

    def test_jsonevent_generation(self, *args, **kwargs):
        actor = _TestActorWrapper(self.__test_class__("eventgenerator", interval=1, delay=0, event_class=JSONEvent))
        _output = actor.output
        self.assertIsInstance(_output, JSONEvent)

    def test_attribute_generation(self, *args, **kwargs):
        actor = _TestActorWrapper(self.__test_class__("eventgenerator", interval=1, delay=0, event_class=Event, event_kwargs={"test_kwarg": "value"}))
        _output = actor.output
        self.assertEqual(_output.test_kwarg, "value")


class TestCallbackEventGenerator(unittest.TestCase):
    __test_class__ = CallbackEventGenerator

    def test_inheritance(self):
        self.assertEqual(len(self.__test_class__.__bases__), 2)
        self.assertEqual(self.__test_class__.__bases__[0], IntervalSchedulingMixin)
        self.assertEqual(self.__test_class__.__bases__[1], CallbackScheduledEventProducer)

class TestUDPEventGenerator(unittest.TestCase):
    __test_class__ = UDPEventGenerator

    def test_inheritance(self):
        self.assertEqual(len(self.__test_class__.__bases__), 2)
        self.assertEqual(self.__test_class__.__bases__[0], IntervalSchedulingMixin)
        self.assertEqual(self.__test_class__.__bases__[1], ScheduledUDPEventProducer)

class TestCronEventGenerator(unittest.TestCase):
    __test_class__ = CronEventGenerator

    def test_inheritance(self):
        self.assertEqual(len(self.__test_class__.__bases__), 2)
        self.assertEqual(self.__test_class__.__bases__[0], CronSchedulingMixin)
        self.assertEqual(self.__test_class__.__bases__[1], ScheduledEventProducer)

class TestUDPCronEventGenerator(unittest.TestCase):
    __test_class__ = UDPCronEventGenerator

    def test_inheritance(self):
        self.assertEqual(len(self.__test_class__.__bases__), 2)
        self.assertEqual(self.__test_class__.__bases__[0], CronSchedulingMixin)
        self.assertEqual(self.__test_class__.__bases__[1], ScheduledUDPEventProducer)