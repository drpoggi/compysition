import unittest
import abc
import gevent
import time

from gevent.event import Event as GEvent
from copy import deepcopy

from compysition.actor import Actor
from compysition.event import Event
from compysition.queue import QueuePool, Queue
from compysition.logger import Logger
from compysition.restartlet import RestartPool
from compysition.errors import (QueueConnected, InvalidActorOutput, QueueEmpty, InvalidEventConversion, 
    InvalidActorInput, QueueFull)

class MockEvent:
    def clone(self): return self
    def xclone(self, iterator):
        for value in iterator:
            yield self, value

class SubEvent(Event):
    def __init__(self, *args, **kwargs):
        self.converted = False
        self.raise_invalid = False
        self.raise_reg_exception = False
        super(SubEvent, self).__init__(*args, **kwargs)

    def mock_convert(self, convert_to):
        if self.raise_invalid:
            raise InvalidActorInput()
        if self.raise_reg_exception:
            raise Exception()
        self.converted = True
        return self

class SubSubEvent(SubEvent):
    pass

class MockException(Exception):
    pass

class MockLogger:
    def __init__(self, *args, **kwargs):
        self.errored = 0
        self.error_msg = None
        self.warned = 0
        self.warn_msg = None
        self.infoed = 0
        self.info_msg = None
        self.debuged = 0
        self.debug_msg = None

    def error(self, data, *args, **kwargs):
        self.errored += 1
        self.error_msg = data

    def warning(self, data, *args, **kwargs):
        self.warned += 1
        self.warn_msg = data

    def info(self, data, *args, **kwargs):
        self.infoed += 1
        self.info_msg = data

    def debug(self, data, *args, **kwargs):
        self.debuged += 1
        self.debug_msg = data

class MockedAsyncClass:
    cleared = False
    waited = False
    running = False

    def clear(self):
        self.cleared = True

    def wait(self):
        self.waited = True

    def is_set(self):
        return self.running

    def set(self):
        self.running = True

class MockedQueue(Queue):
    def __init__(self, *args, **kwargs):
        self.current_loop_count = 0
        self.target_loop_count = 0
        self.add_content_kwargs = {}
        self.add_content_args = []
        self.add_content_actor = None
        self.wait = False
        super(MockedQueue, self).__init__(*args, **kwargs)

    def set_add_content_kwargs(self, actor, *args, **kwargs):
        self.add_content_actor = actor
        self.add_content_args = args
        self.add_content_kwargs = kwargs

    def mock_queue_wait_until_content(self):
        self.current_loop_count += 1
        if self.current_loop_count >= self.target_loop_count:
            if self.wait:
                self._Queue__has_content.wait()
            self.add_content_actor._Actor__loop = False

class MockedActor(Actor):
    _async_class = MockedAsyncClass
    
    cleared_all = False

    def __init__(self, *args, **kwargs):
        self.sent = 0
        self._send_queues = []
        self._send_events = []
        self.consumed = False
        self.consumed_event = None
        self.consumed_kwargs = {}
        self.consumed_args = []
        self.consuming = False
        self.consumed_events = []
        self.pre_hooked = False
        self.post_hooked = False
        self.looping_send = False
        self._looping_event = None
        self._looping_queues = None
        self._looping_check_output = None
        self.threaded = False
        self.did_consume = 0
        self.current_loop_count = 0
        self.target_loop_count = 0
        self.ensured = 0
        self.ensured_datas = []
        self.process_consumer_function = None
        self.process_consumer_queue = None
        self.process_consumer_timeout = None
        self.process_consumer_raise_on_empty = None
        self.get_queued_event_queue = None
        self.get_queued_event_timeout = None
        self.raise_error = QueueEmpty
        self.dest_queue = None
        self.send_error_event = []
        super(MockedActor, self).__init__(*args, **kwargs)


    def consume(self, event, *args, **kwargs):
        self.consumed = True
        self.consumed_event = event
        self.consumed_kwargs = kwargs
        self.consumed_args = args

    def consume_alt(self, event, *args, **kwargs):
        self.dest_queue.put(event, block=False)

    def mock_send_error(self, event):
        self.send_error_event.append(event)

    def _clear_all(self):
        self.cleared_all = True
        super(MockedActor, self)._clear_all()

    def mock__consumer(self, function, queue):
        self.consuming = True

    def mock_pre_hook(self):
        self.pre_hooked = True

    def mock_post_hook(self):
        self.post_hooked = True

    def mock_loop_send(self, event, queues, check_output):
        self.looping_send = True
        self._looping_event = event
        self._looping_queues = queues
        self._looping_check_output = check_output

    def mock_send(self, queue, event):
        self.sent += 1
        self._send_queues.append(queue)
        self._send_events.append(event)

    def mock_thread_func(self):
        self.threaded = True

    def mock_do_consume(self, function, event, queue):
        self.did_consume += 1
        self.consumed_events.append(event)

    def mock_modify_content(self, queue, put_event=True, pull_event=False):
        gevent.sleep(2)
        if put_event:
            queue.put('mock_event')
        if pull_event:
            queue.get()
        self.current_loop_count += 1
        if self.current_loop_count >= self.target_loop_count:
            self._Actor__loop = False

    def mock_process_consumer_event(self, function=None, queue=None, timeout=None, raise_on_empty=None):
        self.process_consumer_function = function
        self.process_consumer_queue = queue
        self.process_consumer_timeout = timeout
        self.process_consumer_raise_on_empty = raise_on_empty

    def mock_process_consumer_event_alt_2(self, function=None, queue=None, timeout=None, raise_on_empty=None):
        self.mock_process_consumer_event(function=function, queue=queue, timeout=timeout, raise_on_empty=raise_on_empty)
        raise MockException()

    def mock_process_consumer_event_alt(self, function=None, queue=None, timeout=None, raise_on_empty=None):
        raise self.raise_error()

    def mock_get_queued_event(self, queue=None, timeout=None):
        self.get_queued_event_queue = queue
        self.get_queued_event_timeout = timeout

    def mock_ensure_tuple(self, data):
        self.ensured += 1
        self.ensured_datas.append(data)
        return self.placholder_ensure_tuple(data=data)

class TestActor(unittest.TestCase):
    def test_init(self):
        #default class values
        self.assertEqual(Actor.__metaclass__, abc.ABCMeta)
        self.assertEqual(Actor.DEFAULT_EVENT_SERVICE, "default")
        self.assertEqual(Actor.input, Event)
        self.assertEqual(Actor.output, Event)
        self.assertEqual(Actor.REQUIRED_EVENT_ATTRIBUTES, None)
        self.assertEqual(Actor._async_class, GEvent)

        #missing name
        with self.assertRaises(TypeError):
            MockedActor()

        #default values
        self.assertEqual(MockedActor.cleared_all, False)
        actor = MockedActor('actor')
        self.assertEqual(actor.blockdiag_config, {"shape": "box"})
        self.assertEqual(actor.name, 'actor')
        self.assertEqual(actor.size, 0)
        self.assertIsInstance(actor.pool, QueuePool)
        self.assertEqual(actor.pool.size, 0)
        self.assertIsInstance(actor.logger, Logger)
        self.assertEqual(actor.logger.name, 'actor')
        self.assertEqual(actor._Actor__loop, True)
        self.assertIsInstance(actor.threads, RestartPool)
        self.assertEqual(actor.threads.logger, actor.logger)
        self.assertEqual(actor.threads.sleep_interval, 1)
        self.assertIsInstance(actor._Actor__run, MockedAsyncClass)
        self.assertIsInstance(actor._Actor__block, MockedAsyncClass)
        self.assertEqual(actor.cleared_all, True)
        self.assertEqual(actor._Actor__blocking_consume, False)
        self.assertEqual(actor.rescue, False)
        self.assertEqual(actor.max_rescue, 5)

        #test name parameter
        self.assertEqual(MockedActor.cleared_all, False)
        actor = MockedActor('some_other_name')
        self.assertEqual(actor.blockdiag_config, {"shape": "box"})
        self.assertEqual(actor.name, 'some_other_name')
        self.assertEqual(actor.size, 0)
        self.assertIsInstance(actor.pool, QueuePool)
        self.assertEqual(actor.pool.size, 0)
        self.assertIsInstance(actor.logger, Logger)
        self.assertEqual(actor.logger.name, 'some_other_name')
        self.assertEqual(actor._Actor__loop, True)
        self.assertIsInstance(actor.threads, RestartPool)
        self.assertEqual(actor.threads.logger, actor.logger)
        self.assertEqual(actor.threads.sleep_interval, 1)
        self.assertIsInstance(actor._Actor__run, MockedAsyncClass)
        self.assertIsInstance(actor._Actor__block, MockedAsyncClass)
        self.assertEqual(actor.cleared_all, True)
        self.assertEqual(actor._Actor__blocking_consume, False)
        self.assertEqual(actor.rescue, False)
        self.assertEqual(actor.max_rescue, 5)

        #test size parameter
        actor = MockedActor('actor', size=2)
        self.assertEqual(actor.blockdiag_config, {"shape": "box"})
        self.assertEqual(actor.name, 'actor')
        self.assertEqual(actor.size, 2)
        self.assertIsInstance(actor.pool, QueuePool)
        self.assertEqual(actor.pool.size, 2)
        self.assertIsInstance(actor.logger, Logger)
        self.assertEqual(actor.logger.name, 'actor')
        self.assertEqual(actor._Actor__loop, True)
        self.assertIsInstance(actor.threads, RestartPool)
        self.assertEqual(actor.threads.logger, actor.logger)
        self.assertEqual(actor.threads.sleep_interval, 1)
        self.assertIsInstance(actor._Actor__run, MockedAsyncClass)
        self.assertIsInstance(actor._Actor__block, MockedAsyncClass)
        self.assertEqual(actor.cleared_all, True)
        self.assertEqual(actor._Actor__blocking_consume, False)
        self.assertEqual(actor.rescue, False)
        self.assertEqual(actor.max_rescue, 5)

        #default blocking consume parameter
        actor = MockedActor('actor', blocking_consume=True)
        self.assertEqual(actor.blockdiag_config, {"shape": "box"})
        self.assertEqual(actor.name, 'actor')
        self.assertEqual(actor.size, 0)
        self.assertIsInstance(actor.pool, QueuePool)
        self.assertEqual(actor.pool.size, 0)
        self.assertIsInstance(actor.logger, Logger)
        self.assertEqual(actor.logger.name, 'actor')
        self.assertEqual(actor._Actor__loop, True)
        self.assertIsInstance(actor.threads, RestartPool)
        self.assertEqual(actor.threads.logger, actor.logger)
        self.assertEqual(actor.threads.sleep_interval, 1)
        self.assertIsInstance(actor._Actor__run, MockedAsyncClass)
        self.assertIsInstance(actor._Actor__block, MockedAsyncClass)
        self.assertEqual(actor.cleared_all, True)
        self.assertEqual(actor._Actor__blocking_consume, True)
        self.assertEqual(actor.rescue, False)
        self.assertEqual(actor.max_rescue, 5)

        #default rescue parameter
        actor = MockedActor('actor', rescue=True)
        self.assertEqual(actor.blockdiag_config, {"shape": "box"})
        self.assertEqual(actor.name, 'actor')
        self.assertEqual(actor.size, 0)
        self.assertIsInstance(actor.pool, QueuePool)
        self.assertEqual(actor.pool.size, 0)
        self.assertIsInstance(actor.logger, Logger)
        self.assertEqual(actor.logger.name, 'actor')
        self.assertEqual(actor._Actor__loop, True)
        self.assertIsInstance(actor.threads, RestartPool)
        self.assertEqual(actor.threads.logger, actor.logger)
        self.assertEqual(actor.threads.sleep_interval, 1)
        self.assertIsInstance(actor._Actor__run, MockedAsyncClass)
        self.assertIsInstance(actor._Actor__block, MockedAsyncClass)
        self.assertEqual(actor.cleared_all, True)
        self.assertEqual(actor._Actor__blocking_consume, False)
        self.assertEqual(actor.rescue, True)
        self.assertEqual(actor.max_rescue, 5)

         #default max_rescue parameter
        actor = MockedActor('actor', max_rescue=2)
        self.assertEqual(actor.blockdiag_config, {"shape": "box"})
        self.assertEqual(actor.name, 'actor')
        self.assertEqual(actor.size, 0)
        self.assertIsInstance(actor.pool, QueuePool)
        self.assertEqual(actor.pool.size, 0)
        self.assertIsInstance(actor.logger, Logger)
        self.assertEqual(actor.logger.name, 'actor')
        self.assertEqual(actor._Actor__loop, True)
        self.assertIsInstance(actor.threads, RestartPool)
        self.assertEqual(actor.threads.logger, actor.logger)
        self.assertEqual(actor.threads.sleep_interval, 1)
        self.assertIsInstance(actor._Actor__run, MockedAsyncClass)
        self.assertIsInstance(actor._Actor__block, MockedAsyncClass)
        self.assertEqual(actor.cleared_all, True)
        self.assertEqual(actor._Actor__blocking_consume, False)
        self.assertEqual(actor.rescue, False)
        self.assertEqual(actor.max_rescue, 2)

    def test_block(self):
        actor = MockedActor('actor')
        self.assertEqual(actor._Actor__block.waited, False)
        actor.block()
        self.assertEqual(actor._Actor__block.waited, True)

    def perform_queue_test(self, 
        post_src_err=0, post_src_in=0, post_src_out=0, post_src_log=1,
        post_dest_err=0, post_dest_in=0, post_dest_out=0, post_dest_log=1,
        source_queue_name=None, destination_queue_name=None, pool_scope_name=None, check_exists=None, destination=None,
        test_inbox_name="", test_src_pool_name="", test_outbox_name="", test_dest_pool_name="",
        func_name=""
        ):

        #test default destination queue name
        source_actor = MockedActor('source_name')
        destination_actor = MockedActor('destination_name')

        kwargs = {}
        kwargs["destination"] = destination_actor
        if source_queue_name:
            kwargs["source_queue_name"] = source_queue_name
        if destination_queue_name:
            kwargs["destination_queue_name"] = destination_queue_name
        if pool_scope_name:
            kwargs["pool_scope"] = getattr(source_actor.pool, pool_scope_name)
        if check_exists:
            kwargs["check_exists"] = check_exists
        if destination:
            kwargs["destination"] = destination

        self.assertEqual(len(source_actor.pool.error), 0)
        self.assertEqual(len(source_actor.pool.inbound), 0)
        self.assertEqual(len(source_actor.pool.outbound), 0)
        self.assertEqual(len(source_actor.pool.logs), 1)
        self.assertEqual(len(destination_actor.pool.error), 0)
        self.assertEqual(len(destination_actor.pool.inbound), 0)
        self.assertEqual(len(destination_actor.pool.outbound), 0)
        self.assertEqual(len(destination_actor.pool.logs), 1)
        self.assertNotEqual(source_actor.pool.logs.get(source_actor.pool.logs.placeholder, None), None)
        self.assertNotEqual(destination_actor.pool.logs.get(destination_actor.pool.logs.placeholder, None), None)
        getattr(source_actor, func_name)(**kwargs)
        self.assertEqual(len(source_actor.pool.error), post_src_err)
        self.assertEqual(len(source_actor.pool.inbound), post_src_in)
        self.assertEqual(len(source_actor.pool.outbound), post_src_out)
        self.assertEqual(len(source_actor.pool.logs), post_src_log)
        self.assertEqual(len(destination_actor.pool.error), post_dest_err)
        self.assertEqual(len(destination_actor.pool.inbound), post_dest_in)
        self.assertEqual(len(destination_actor.pool.outbound), post_dest_out)
        self.assertEqual(len(destination_actor.pool.logs), post_dest_log)
        self.assertEqual(getattr(source_actor.pool, test_src_pool_name).get(test_outbox_name), 
            getattr(destination_actor.pool, test_dest_pool_name).get(test_inbox_name))
        self.assertIsInstance(getattr(source_actor.pool, test_src_pool_name).get(test_outbox_name), Queue)

    def test_connect_error_queue(self):
        #test default destination queue name
        self.perform_queue_test(post_src_err=1, post_dest_in=1, test_inbox_name="error_inbox", 
            test_src_pool_name="error", test_outbox_name="outbox", test_dest_pool_name="inbound",
            func_name="connect_error_queue")

        #test missing destination
        source_actor = MockedActor('source_name')
        with self.assertRaises(AttributeError):
            source_actor.connect_error_queue()

        #test destination queue name parameter
        self.perform_queue_test(post_src_err=1, post_dest_in=1, test_inbox_name="error_destination_queue_name", 
            test_src_pool_name="error", test_outbox_name="outbox", test_dest_pool_name="inbound",
            destination_queue_name="destination_queue_name", func_name="connect_error_queue")


    def test_connect_log_queue(self):
        #test default destination queue name
        self.perform_queue_test(post_src_log=1, post_dest_in=1, test_inbox_name="log_inbox", 
            test_src_pool_name="logs", test_outbox_name="outbox", test_dest_pool_name="inbound",
            func_name="connect_log_queue")

        #test missing destination
        source_actor = MockedActor('source_name')
        with self.assertRaises(AttributeError):
            source_actor.connect_log_queue()

        #test destination queue name parameter
        self.perform_queue_test(post_src_log=1, post_dest_in=1, test_inbox_name="log_destination_queue_name", 
            test_src_pool_name="logs", test_outbox_name="outbox", test_dest_pool_name="inbound",
            destination_queue_name="destination_queue_name", func_name="connect_log_queue")

    def test_connect_queue(self):
        #test default destination queue name
        self.perform_queue_test(post_src_out=1, post_dest_in=1, test_inbox_name="inbox", 
            test_src_pool_name="outbound", test_outbox_name="outbox", test_dest_pool_name="inbound",
            func_name="connect_queue")

        #test missing destination
        source_actor = MockedActor('source_name')
        with self.assertRaises(AttributeError):
            source_actor.connect_queue()

        #test destination queue name parameter
        self.perform_queue_test(post_src_out=1, post_dest_in=1, test_inbox_name="destination_queue_name", 
            test_src_pool_name="outbound", test_outbox_name="outbox", test_dest_pool_name="inbound",
            destination_queue_name="destination_queue_name", func_name="connect_queue")

    def test_Actor__connect_queue(self):
        #test destination_queue_name
        self.perform_queue_test(post_src_out=1, post_dest_in=1, test_inbox_name="destination_queue_name", 
            test_src_pool_name="outbound", test_outbox_name="outbox", test_dest_pool_name="inbound",
            destination_queue_name="destination_queue_name", func_name="_Actor__connect_queue",
            pool_scope_name="outbound")

        #test empty destination_queue_name
        ###TODO Queue with key None? Seems illogical to allow this but potentially damaging to dependent systems if altered
        source_actor = MockedActor('source_name')
        destination_actor = MockedActor('destination_name')
        source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
            destination_queue_name=None, source_queue_name="inbox", check_existing=False)
        self.assertEqual(source_actor.pool.outbound.get("inbox"), 
            destination_actor.pool.inbound.get(None))
        self.assertIsInstance(source_actor.pool.outbound.get("inbox"), Queue)

        #test source_queue_name parameter
        self.perform_queue_test(post_src_out=1, post_dest_in=1, test_inbox_name="inbox", 
            test_src_pool_name="outbound", test_outbox_name="source_queue_name", test_dest_pool_name="inbound",
            func_name="_Actor__connect_queue", pool_scope_name="outbound", source_queue_name="source_queue_name")

        #test empty source_queue_name parameter
        ###TODO Queue with key None? Seems illogical to allow this but potentially damaging to dependent systems if altered
        source_actor = MockedActor('source_name')
        destination_actor = MockedActor('destination_name')
        source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
            source_queue_name=None, destination_queue_name="outbox", check_existing=False)
        self.assertEqual(source_actor.pool.outbound.get(None), 
            destination_actor.pool.inbound.get("outbox"))
        self.assertIsInstance(source_actor.pool.outbound.get(None), Queue)

        #test default/missing source_pool parameter
        with self.assertRaises(AttributeError):
            self.perform_queue_test(post_src_out=1, post_dest_in=1, test_inbox_name="inbox", 
                test_src_pool_name="outbound", test_outbox_name="source_queue_name", test_dest_pool_name="inbound",
                func_name="_Actor__connect_queue", source_queue_name="source_queue_name")

        #test missing destination
        source_actor = MockedActor('source_name')
        with self.assertRaises(AttributeError):
            source_actor.connect_queue()

        #test check_existing parameter existing source_queue
        source_actor = MockedActor('source_name')
        destination_actor = MockedActor('destination_name')
        source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
            destination_queue_name="outbox", source_queue_name="inbox", check_existing=True)
        with self.assertRaises(QueueConnected):
            source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
                destination_queue_name="outbox2", source_queue_name="inbox", check_existing=True)

        #test check_existing parameter existing destination_queue
        source_actor = MockedActor('source_name')
        destination_actor = MockedActor('destination_name')
        source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
            destination_queue_name="outbox", source_queue_name="inbox", check_existing=True)
        with self.assertRaises(QueueConnected):
            source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
                destination_queue_name="outbox", source_queue_name="inbox2", check_existing=True)

        #test missing source_queue missing destination queue
        source_actor = MockedActor('source_name')
        destination_actor = MockedActor('destination_name')
        self.assertEqual(len(source_actor.pool.error), 0)
        self.assertEqual(len(source_actor.pool.inbound), 0)
        self.assertEqual(len(source_actor.pool.outbound), 0)
        self.assertEqual(len(source_actor.pool.logs), 1)
        self.assertEqual(len(destination_actor.pool.error), 0)
        self.assertEqual(len(destination_actor.pool.inbound), 0)
        self.assertEqual(len(destination_actor.pool.outbound), 0)
        self.assertEqual(len(destination_actor.pool.logs), 1)
        source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
            destination_queue_name="outbox", source_queue_name="inbox", check_existing=False)
        self.assertEqual(len(source_actor.pool.error), 0)
        self.assertEqual(len(source_actor.pool.inbound), 0)
        self.assertEqual(len(source_actor.pool.outbound), 1)
        self.assertEqual(len(source_actor.pool.logs), 1)
        self.assertEqual(len(destination_actor.pool.error), 0)
        self.assertEqual(len(destination_actor.pool.inbound), 1)
        self.assertEqual(len(destination_actor.pool.outbound), 0)
        self.assertEqual(len(destination_actor.pool.logs), 1)
        self.assertEqual(destination_actor.pool.inbound.get("outbox"), source_actor.pool.outbound.get("inbox"))
        self.assertIsInstance(destination_actor.pool.inbound.get("outbox"), Queue)

        #test missing source_queue existing destination queue
        source_actor = MockedActor('source_name')
        destination_actor = MockedActor('destination_name')
        self.assertEqual(len(source_actor.pool.error), 0)
        self.assertEqual(len(source_actor.pool.inbound), 0)
        self.assertEqual(len(source_actor.pool.outbound), 0)
        self.assertEqual(len(source_actor.pool.logs), 1)
        self.assertEqual(len(destination_actor.pool.error), 0)
        self.assertEqual(len(destination_actor.pool.inbound), 0)
        self.assertEqual(len(destination_actor.pool.outbound), 0)
        self.assertEqual(len(destination_actor.pool.logs), 1)
        source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
            destination_queue_name="outbox", source_queue_name="inbox", check_existing=False)
        self.assertEqual(len(source_actor.pool.error), 0)
        self.assertEqual(len(source_actor.pool.inbound), 0)
        self.assertEqual(len(source_actor.pool.outbound), 1)
        self.assertEqual(len(source_actor.pool.logs), 1)
        self.assertEqual(len(destination_actor.pool.error), 0)
        self.assertEqual(len(destination_actor.pool.inbound), 1)
        self.assertEqual(len(destination_actor.pool.outbound), 0)
        self.assertEqual(len(destination_actor.pool.logs), 1)
        source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
            destination_queue_name="outbox", source_queue_name="inbox2", check_existing=False)
        self.assertEqual(len(source_actor.pool.error), 0)
        self.assertEqual(len(source_actor.pool.inbound), 0)
        self.assertEqual(len(source_actor.pool.outbound), 2)
        self.assertEqual(len(source_actor.pool.logs), 1)
        self.assertEqual(len(destination_actor.pool.error), 0)
        self.assertEqual(len(destination_actor.pool.inbound), 1)
        self.assertEqual(len(destination_actor.pool.outbound), 0)
        self.assertEqual(len(destination_actor.pool.logs), 1)
        self.assertEqual(destination_actor.pool.inbound.get("outbox"), source_actor.pool.outbound.get("inbox"))
        self.assertEqual(destination_actor.pool.inbound.get("outbox"), source_actor.pool.outbound.get("inbox2"))
        self.assertIsInstance(destination_actor.pool.inbound.get("outbox"), Queue)

        #test existing source_queue missing destination queue
        source_actor = MockedActor('source_name')
        destination_actor = MockedActor('destination_name')
        self.assertEqual(len(source_actor.pool.error), 0)
        self.assertEqual(len(source_actor.pool.inbound), 0)
        self.assertEqual(len(source_actor.pool.outbound), 0)
        self.assertEqual(len(source_actor.pool.logs), 1)
        self.assertEqual(len(destination_actor.pool.error), 0)
        self.assertEqual(len(destination_actor.pool.inbound), 0)
        self.assertEqual(len(destination_actor.pool.outbound), 0)
        self.assertEqual(len(destination_actor.pool.logs), 1)
        source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
            destination_queue_name="outbox", source_queue_name="inbox", check_existing=False)
        self.assertEqual(len(source_actor.pool.error), 0)
        self.assertEqual(len(source_actor.pool.inbound), 0)
        self.assertEqual(len(source_actor.pool.outbound), 1)
        self.assertEqual(len(source_actor.pool.logs), 1)
        self.assertEqual(len(destination_actor.pool.error), 0)
        self.assertEqual(len(destination_actor.pool.inbound), 1)
        self.assertEqual(len(destination_actor.pool.outbound), 0)
        self.assertEqual(len(destination_actor.pool.logs), 1)
        source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
            destination_queue_name="outbox2", source_queue_name="inbox", check_existing=False)
        self.assertEqual(len(source_actor.pool.error), 0)
        self.assertEqual(len(source_actor.pool.inbound), 0)
        self.assertEqual(len(source_actor.pool.outbound), 1)
        self.assertEqual(len(source_actor.pool.logs), 1)
        self.assertEqual(len(destination_actor.pool.error), 0)
        self.assertEqual(len(destination_actor.pool.inbound), 2)
        self.assertEqual(len(destination_actor.pool.outbound), 0)
        self.assertEqual(len(destination_actor.pool.logs), 1)
        self.assertEqual(destination_actor.pool.inbound.get("outbox"), source_actor.pool.outbound.get("inbox"))
        self.assertEqual(destination_actor.pool.inbound.get("outbox2"), source_actor.pool.outbound.get("inbox"))
        self.assertIsInstance(destination_actor.pool.inbound.get("outbox"), Queue)

        #test existing source_queue existing destination queue
        source_actor = MockedActor('source_name')
        destination_actor = MockedActor('destination_name')
        self.assertEqual(len(source_actor.pool.error), 0)
        self.assertEqual(len(source_actor.pool.inbound), 0)
        self.assertEqual(len(source_actor.pool.outbound), 0)
        self.assertEqual(len(source_actor.pool.logs), 1)
        self.assertEqual(len(destination_actor.pool.error), 0)
        self.assertEqual(len(destination_actor.pool.inbound), 0)
        self.assertEqual(len(destination_actor.pool.outbound), 0)
        self.assertEqual(len(destination_actor.pool.logs), 1)
        source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
            destination_queue_name="outbox", source_queue_name="inbox", check_existing=False)
        self.assertEqual(len(source_actor.pool.error), 0)
        self.assertEqual(len(source_actor.pool.inbound), 0)
        self.assertEqual(len(source_actor.pool.outbound), 1)
        self.assertEqual(len(source_actor.pool.logs), 1)
        self.assertEqual(len(destination_actor.pool.error), 0)
        self.assertEqual(len(destination_actor.pool.inbound), 1)
        self.assertEqual(len(destination_actor.pool.outbound), 0)
        self.assertEqual(len(destination_actor.pool.logs), 1)
        source_actor._Actor__connect_queue(destination=destination_actor, pool_scope=source_actor.pool.outbound, 
            destination_queue_name="outbox", source_queue_name="inbox", check_existing=False)
        self.assertEqual(len(source_actor.pool.error), 0)
        self.assertEqual(len(source_actor.pool.inbound), 0)
        self.assertEqual(len(source_actor.pool.outbound), 1)
        self.assertEqual(len(source_actor.pool.logs), 1)
        self.assertEqual(len(destination_actor.pool.error), 0)
        self.assertEqual(len(destination_actor.pool.inbound), 1)
        self.assertEqual(len(destination_actor.pool.outbound), 0)
        self.assertEqual(len(destination_actor.pool.logs), 1)
        self.assertEqual(destination_actor.pool.inbound.get("outbox"), source_actor.pool.outbound.get("inbox"))
        self.assertIsInstance(destination_actor.pool.inbound.get("outbox"), Queue)

    def test_loop(self):
        actor = MockedActor('actor')
        actor._Actor__loop = True
        self.assertEqual(actor.loop(), True)
        actor._Actor__loop = False
        self.assertEqual(actor.loop(), False)

    def test_is_running(self):
        actor = MockedActor('actor')
        actor._Actor__run.running = True
        self.assertEqual(actor.is_running(), True)
        actor._Actor__run.running = False
        self.assertEqual(actor.is_running(), False)

    def test_register_consumer(self):
        actor = MockedActor('actor')
        actor._Actor__consumer = actor.mock__consumer
        self.assertEqual(len(actor.pool.inbound), 0)
        self.assertEqual(actor.consuming, False)
        actor.register_consumer(queue_name="test_name", queue=Queue("test_queue"))
        gevent.sleep(0)
        self.assertEqual(len(actor.pool.inbound), 1)
        self.assertEqual(actor.consuming, True)

    def test_ensure_tuple(self):
        #test data not tuple is list
        actor = MockedActor('actor')
        data = [Event]
        self.assertNotIsInstance(data, tuple)
        self.assertIsInstance(data, list)
        data = actor.ensure_tuple(data=data)
        self.assertNotIsInstance(data, list)
        self.assertIsInstance(data, tuple)

        #test data not tuple is other
        actor = MockedActor('actor')
        data = Event
        self.assertNotIsInstance(data, tuple)
        self.assertNotIsInstance(data, list)
        data = actor.ensure_tuple(data=data)
        self.assertNotIsInstance(data, list)
        self.assertIsInstance(data, tuple)
        self.assertNotEqual(data, Event)

        #test data is tuple
        actor = MockedActor('actor')
        data = (Event, )
        self.assertNotIsInstance(data, list)
        self.assertIsInstance(data, tuple)
        data = actor.ensure_tuple(data=data)
        self.assertNotIsInstance(data, list)
        self.assertIsInstance(data, tuple)

    def test_start(self):
        #test input/output tuple
        actor = MockedActor('actor')
        actor.placholder_ensure_tuple = actor.ensure_tuple
        actor.ensure_tuple = actor.mock_ensure_tuple
        actor.output = MockEvent
        ac_in = actor.input
        ac_out = actor.output
        actor.start()
        self.assertEqual(actor.ensured, 2)
        self.assertIs(actor.ensured_datas[0], ac_in)
        self.assertIs(actor.ensured_datas[1], ac_out)
        self.assertIsNot(actor.ensured_datas[1], ac_in)
        self.assertIsNot(actor.ensured_datas[0], ac_out)

        #test pre_hook exists
        actor = MockedActor('actor')
        actor.pre_hook = actor.mock_pre_hook
        getattr(actor, 'pre_hook')
        self.assertEqual(actor.pre_hooked, False)
        actor.start()
        self.assertEqual(actor.pre_hooked, True)

        #test pre_hook doesn't exist
        actor = MockedActor('actor')
        with self.assertRaises(AttributeError):
            getattr(actor, 'pre_hook')
        self.assertEqual(actor.pre_hooked, False)
        actor.start()
        self.assertEqual(actor.pre_hooked, False)

        #test set run
        actor = MockedActor('actor')
        self.assertEqual(actor._Actor__run.running, False)
        actor.start()
        self.assertEqual(actor._Actor__run.running, True)

    def test_stop(self):
        #test __loop changing
        actor = MockedActor('actor')
        self.assertEqual(actor._Actor__loop, True)
        actor.stop()
        self.assertEqual(actor._Actor__loop, False)
        actor.stop()
        self.assertEqual(actor._Actor__loop, False)

        #test set block
        actor = MockedActor('actor')
        self.assertEqual(actor._Actor__block.running, False)
        actor.stop()
        self.assertEqual(actor._Actor__block.running, True)

        #test post_hook exists
        actor = MockedActor('actor')
        actor.post_hook = actor.mock_post_hook
        getattr(actor, 'post_hook')
        self.assertEqual(actor.post_hooked, False)
        actor.stop()
        self.assertEqual(actor.post_hooked, True)

        #test post_hook doesn't exist
        actor = MockedActor('actor')
        with self.assertRaises(AttributeError):
            getattr(actor, 'post_hook')
        self.assertEqual(actor.post_hooked, False)
        actor.stop()
        self.assertEqual(actor.post_hooked, False)

    def test_send_event(self):
        #test missing event
        actor = MockedActor('actor')
        actor._loop_send = actor.mock_loop_send
        with self.assertRaises(TypeError):
            actor.send_event()

        #test defaults and execution of _loop_send
        actor = MockedActor('actor')
        actor._loop_send = actor.mock_loop_send
        event = Event()
        self.assertEqual(actor.looping_send, False)
        self.assertEqual(actor._looping_event, None)
        self.assertEqual(actor._looping_check_output, None)
        actor.send_event(event)
        self.assertEqual(actor.looping_send, True)
        self.assertEqual(actor._looping_event, event)
        self.assertEqual(actor._looping_check_output, True)

        #test queues parameter
        actor = MockedActor('actor')
        actor._loop_send = actor.mock_loop_send
        event = Event()
        self.assertEqual(actor.looping_send, False)
        self.assertEqual(actor._looping_event, None)
        self.assertEqual(actor._looping_queues, None)
        self.assertEqual(actor._looping_check_output, None)
        actor.send_event(event, queues="some_queues")
        self.assertEqual(actor.looping_send, True)
        self.assertEqual(actor._looping_event, event)
        self.assertEqual(actor._looping_queues, "some_queues")
        self.assertEqual(actor._looping_check_output, True)

        #test get queues
        actor = MockedActor('actor')
        actor._loop_send = actor.mock_loop_send
        event = Event()
        actor.pool.outbound = "outboud_queues"
        self.assertEqual(actor.looping_send, False)
        self.assertEqual(actor._looping_event, None)
        self.assertEqual(actor._looping_queues, None)
        self.assertEqual(actor._looping_check_output, None)
        actor.send_event(event)
        self.assertEqual(actor.looping_send, True)
        self.assertEqual(actor._looping_event, event)
        self.assertEqual(actor._looping_queues, "outboud_queues")
        self.assertEqual(actor._looping_check_output, True)

        #test checkout_output True
        actor = MockedActor('actor')
        actor._loop_send = actor.mock_loop_send
        event = Event()
        self.assertEqual(actor.looping_send, False)
        self.assertEqual(actor._looping_event, None)
        self.assertEqual(actor._looping_check_output, None)
        actor.send_event(event, check_output=True)
        self.assertEqual(actor.looping_send, True)
        self.assertEqual(actor._looping_event, event)
        self.assertEqual(actor._looping_check_output, True)
        
        #test checkout_output False
        actor = MockedActor('actor')
        actor._loop_send = actor.mock_loop_send
        event = Event()
        self.assertEqual(actor.looping_send, False)
        self.assertEqual(actor._looping_event, None)
        self.assertEqual(actor._looping_check_output, None)
        actor.send_event(event, check_output=False)
        self.assertEqual(actor.looping_send, True)
        self.assertEqual(actor._looping_event, event)
        self.assertEqual(actor._looping_check_output, False)

    def test_send_all(self):
        from compysition.errors import QueueEmpty, QueueFull
        class MockActor(Actor):
            def consume(self): pass
        event = Event()
        queue_names = ["a", "b", "c", "d", "e"]
        queues = [Queue(name) for name in queue_names]
        actor = MockActor("actor")
        actor._send_all(queues=queues, event=event)
        queued_events = [queue.get() for queue in queues]
        for qevent in queued_events:
            assert event is not qevent
            assert event.__getstate__() == qevent.__getstate__()

    def _clean_queues(self, queues):
        try:
            iterator = queues.itervalues()
        except AttributeError:
            iterator = queues
        for queue in iterator:
            for _ in xrange(queue.qsize()):
                queue.get()

    def _time_send_all(self, actor, queues, event, iterations=2500):
        cur = time.time() - time.time()
        for _ in range(iterations):
            self._clean_queues(queues=queues)
            start = time.time()
            actor._send_all(queues=queues, event=event)
            cur += (time.time()-start)
        return cur

    def _test_send_all_speed(self):
        func = lambda event: deepcopy(event)
        func = lambda event: event.clone()
        class OldActor(Actor):
            #old functionality
            def _send_all(self, queues, event):
                try:
                    for queue in queues.itervalues():
                        self._send(queue, func(event))
                except AttributeError:
                    for queue in queues:
                        self._send(queue, func(event))
            def consume(self): pass
        class NewActor(Actor):
            def consume(self): pass
        event, old_actor, actor = Event(), OldActor("old"), NewActor("new")
        queue_names = ["a", "b", "c", "d", "e"]
        queues = [Queue(name) for name in queue_names]
        queue_map = dict(zip(queue_names, queues))
        print("1")
        print("old vs new", 
            self._time_send_all(actor=old_actor, queues=queues, event=event), 
            self._time_send_all(actor=actor, queues=queues, event=event)
            )
        print("old vs new", 
            self._time_send_all(actor=old_actor, queues=queue_map, event=event), 
            self._time_send_all(actor=actor, queues=queue_map, event=event)
            )
        queues = queues[:1]
        queue_map = dict((next(queue_map.iteritems()),))
        print("old vs new", 
            self._time_send_all(actor=old_actor, queues=queues, event=event), 
            self._time_send_all(actor=actor, queues=queues, event=event)
            )
        print("old vs new", 
            self._time_send_all(actor=old_actor, queues=queue_map, event=event), 
            self._time_send_all(actor=actor, queues=queue_map, event=event)
            )

    def test_send_error(self):
        #test missing event
        actor = MockedActor('actor')
        actor._loop_send = actor.mock_loop_send
        with self.assertRaises(TypeError):
            actor.send_event()

        #test defaults and execution of _loop_send
        actor = MockedActor('actor')
        actor._loop_send = actor.mock_loop_send
        event = Event()
        self.assertEqual(actor.looping_send, False)
        self.assertEqual(actor._looping_event, None)
        self.assertEqual(actor._looping_queues, None)
        self.assertEqual(actor._looping_check_output, None)
        actor.send_error(event)
        self.assertEqual(actor.looping_send, True)
        self.assertEqual(actor._looping_event, event)
        self.assertEqual(actor._looping_queues, actor.pool.error)
        self.assertEqual(actor._looping_check_output, False)

    def test_loop_send(self):
        #test missing parameters
        actor = MockedActor('actor')
        actor._send = actor.mock_send
        with self.assertRaises(TypeError):
            actor._loop_send()
        with self.assertRaises(TypeError):
            actor._loop_send(event=Event())
        with self.assertRaises(TypeError):
            actor._loop_send(queues="something")
        actor._loop_send(event=Event(), queues="something")

        #test checkout = True; event in self.output
        actor = MockedActor('actor')
        actor._send = actor.mock_send
        self.assertEqual(actor.output, Event)
        actor._loop_send(event=Event(), queues="queues", check_output=True)
        actor._loop_send(event=SubEvent(), queues="queues", check_output=True)
        actor._loop_send(event=Event(), queues="queues")
        actor._loop_send(event=SubEvent(), queues="queues")

        #test checkout = True; event not in self.output
        actor = MockedActor('actor')
        actor._send = actor.mock_send
        self.assertEqual(actor.output, Event)
        with self.assertRaises(InvalidActorOutput):
            actor._loop_send(event=MockEvent(), queues="queues", check_output=True)
        with self.assertRaises(InvalidActorOutput):
            actor._loop_send(event=MockEvent(), queues="queues")

        #test checkout = False; event in self.output
        actor = MockedActor('actor')
        actor._send = actor.mock_send
        self.assertEqual(actor.output, Event)
        actor._loop_send(event=Event(), queues="queues", check_output=False)
        actor._loop_send(event=SubEvent(), queues="queues", check_output=False)

        #test checkout = False; event not in self.output
        actor = MockedActor('actor')
        actor._send = actor.mock_send
        self.assertEqual(actor.output, Event)
        actor._loop_send(event=MockEvent(), queues="queues", check_output=False)

        #test queues is dict
        actor = MockedActor('actor')
        actor._send = actor.mock_send
        self.assertEqual(actor.sent, 0)
        self.assertEqual(len(actor._send_queues), 0)
        self.assertEqual(len(actor._send_events), 0)
        actor._loop_send(event=Event(), queues={"k1": 3, "k2": 10})
        self.assertEqual(actor.sent, 2)
        self.assertEqual(len(actor._send_queues), 2)
        self.assertEqual(len(actor._send_events), 2)
        self.assertTrue(3 in actor._send_queues)
        self.assertTrue(10 in actor._send_queues)
        self.assertEqual(actor._send_events[0]._event_id, actor._send_events[1]._event_id)

        #test queues is list
        actor = MockedActor('actor')
        actor._send = actor.mock_send
        self.assertEqual(actor.sent, 0)
        self.assertEqual(len(actor._send_queues), 0)
        self.assertEqual(len(actor._send_events), 0)
        actor._loop_send(event=Event(), queues=[2,7,18])
        self.assertEqual(actor.sent, 3)
        self.assertEqual(len(actor._send_queues), 3)
        self.assertEqual(len(actor._send_events), 3)
        self.assertTrue(2 in actor._send_queues)
        self.assertTrue(7 in actor._send_queues)
        self.assertTrue(18 in actor._send_queues)
        self.assertEqual(actor._send_events[0]._event_id, actor._send_events[1]._event_id)
        self.assertEqual(actor._send_events[0]._event_id, actor._send_events[2]._event_id)

        #test queues is tuple
        actor = MockedActor('actor')
        actor._send = actor.mock_send
        self.assertEqual(actor.sent, 0)
        self.assertEqual(len(actor._send_queues), 0)
        self.assertEqual(len(actor._send_events), 0)
        actor._loop_send(event=Event(), queues=(1,65,34,54))
        self.assertEqual(actor.sent, 4)
        self.assertEqual(len(actor._send_queues), 4)
        self.assertEqual(len(actor._send_events), 4)
        self.assertTrue(1 in actor._send_queues)
        self.assertTrue(65 in actor._send_queues)
        self.assertTrue(34 in actor._send_queues)
        self.assertTrue(54 in actor._send_queues)
        self.assertEqual(actor._send_events[0]._event_id, actor._send_events[1]._event_id)
        self.assertEqual(actor._send_events[0]._event_id, actor._send_events[2]._event_id)
        self.assertEqual(actor._send_events[0]._event_id, actor._send_events[3]._event_id)

        #test queues is other
        actor = MockedActor('actor')
        actor._send = actor.mock_send
        self.assertEqual(actor.sent, 0)
        self.assertEqual(len(actor._send_queues), 0)
        self.assertEqual(len(actor._send_events), 0)
        with self.assertRaises(TypeError):
            actor._loop_send(event=Event(), queues=object())

    def test_send(self):
        #test adding event to queue
        actor = MockedActor('actor')
        queue = Queue("queue_name")
        event = Event()
        actor._send(queue=queue, event=event)
        self.assertEqual(queue.get(), event)
        with self.assertRaises(QueueEmpty):
            queue.get()

        #test without seperate thread
        actor = MockedActor('actor')
        queue = Queue("queue_name")
        event = Event()
        self.assertEqual(actor.threaded, False)
        actor._send(queue=queue, event=event)
        self.assertEqual(actor.threaded, False)

        #test with seperate thread
        actor = MockedActor('actor')
        queue = Queue("queue_name")
        event = Event()
        threads = RestartPool()
        threads.spawn(actor.mock_thread_func)
        self.assertEqual(actor.threaded, False)
        actor._send(queue=queue, event=event)
        self.assertEqual(actor.threaded, True)

    def test_consumer_1(self):
        #test defaults
        actor = MockedActor('actor')
        actor._Actor__process_consumer_event = actor.mock_process_consumer_event
        queue = Queue("some queue")
        with self.assertRaises(TypeError):
            actor._Actor__consumer()
        with self.assertRaises(TypeError):
            actor._Actor__consumer(function="some_function")
        with self.assertRaises(TypeError):
            actor._Actor__consumer(queue=queue)
        with self.assertRaises(AttributeError):
            actor._Actor__consumer(function="some_function", queue="some_function")
        with self.assertRaises(gevent.hub.LoopExit):
            actor._Actor__consumer(function="some_function", queue=queue)

    def test_consumer_2(self):
        #test run wait
        actor = MockedActor('actor')
        actor._Actor__process_consumer_event = actor.mock_process_consumer_event
        actor._Actor__loop = False
        queue = Queue('queue_name')
        queue.put(Event())
        actor._Actor__blocking_consume = True
        self.assertEqual(actor._Actor__run.waited, False)
        actor._Actor__consumer(function=None, queue=queue, ensure_empty=False)
        self.assertEqual(actor._Actor__run.waited, True)

    def test_consumer_3(self):
        #test wait until content (fail)
        actor = MockedActor('actor')
        actor._Actor__process_consumer_event = actor.mock_process_consumer_event
        actor._Actor__loop = True
        actor.target_loop_count = 1

        queue = Queue('queue_name')
        
        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.did_consume, 0)
        self.assertEqual(len(actor.consumed_events), 0)
        self.assertEqual(actor._Actor__loop, True)

        with self.assertRaises(gevent.hub.LoopExit):
            #infinite loop as no content is added
            actor._Actor__consumer(function=None, queue=queue, ensure_empty=False)

    def test_consumer_4(self):
        #test wait until content (success)
        actor = MockedActor('actor')
        actor._Actor__process_consumer_event = actor.mock_process_consumer_event
        actor._Actor__loop = True
        actor.target_loop_count = 1

        queue = Queue('queue_name')

        actor.threads.spawn(actor.mock_modify_content, queue=queue)
        start = time.time()

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.did_consume, 0)
        self.assertEqual(len(actor.consumed_events), 0)
        self.assertEqual(actor._Actor__loop, True)

        self.assertEqual(actor.process_consumer_function, None)
        self.assertEqual(actor.process_consumer_queue, None)
        self.assertEqual(actor.process_consumer_timeout, None)
        self.assertEqual(actor.process_consumer_raise_on_empty, None)

        actor._Actor__consumer(function="some function", queue=queue, timeout=5, ensure_empty=False)

        end = time.time()
        dif = end - start

        self.assertEqual(queue._Queue__has_content.ready(), True)
        self.assertEqual(queue.qsize(), 1)
        self.assertEqual(actor.did_consume, 0)
        self.assertEqual(len(actor.consumed_events), 0)
        self.assertEqual(actor._Actor__loop, False)
        self.assertGreater(dif, 1)
        self.assertGreater(3, dif)

        self.assertEqual(actor.process_consumer_function, "some function")
        self.assertNotEqual(actor.process_consumer_queue, Queue("some_other_name_1"))
        self.assertIsNot(actor.process_consumer_queue, Queue("some_other_name_2"))
        self.assertIs(actor.process_consumer_queue, queue)
        self.assertEqual(actor.process_consumer_timeout, 5)
        self.assertEqual(actor.process_consumer_raise_on_empty, None)

    def test_consumer_5(self):
        #test ensure_empty qsize = 0
        actor = MockedActor('actor')
        actor._Actor__process_consumer_event = actor.mock_process_consumer_event
        actor._Actor__loop = False
        queue = Queue('queue_name')

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.process_consumer_function, None)
        self.assertEqual(actor.process_consumer_queue, None)
        self.assertEqual(actor.process_consumer_timeout, None)
        self.assertEqual(actor.process_consumer_raise_on_empty, None)

        actor._Actor__consumer(function="some function", queue=queue, timeout=5, ensure_empty=True)

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.process_consumer_function, None)
        self.assertEqual(actor.process_consumer_queue, None)
        self.assertEqual(actor.process_consumer_timeout, None)
        self.assertEqual(actor.process_consumer_raise_on_empty, None)

        #test ensure_empty qsize > 0
        actor = MockedActor('actor')
        actor._Actor__process_consumer_event = actor.mock_process_consumer_event_alt_2
        actor._Actor__loop = False
        queue = Queue('queue_name')

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.process_consumer_function, None)
        self.assertEqual(actor.process_consumer_queue, None)
        self.assertEqual(actor.process_consumer_timeout, None)
        self.assertEqual(actor.process_consumer_raise_on_empty, None)

        queue.put("some_event")

        self.assertEqual(queue._Queue__has_content.ready(), True)
        self.assertEqual(queue.qsize(), 1)

        with self.assertRaises(MockException):
            actor._Actor__consumer(function="some function", queue=queue, timeout=5, ensure_empty=True)

        self.assertEqual(queue._Queue__has_content.ready(), True)
        self.assertEqual(queue.qsize(), 1)
        self.assertEqual(actor.process_consumer_function, "some function")
        self.assertNotEqual(actor.process_consumer_queue, Queue("some_other_name_1"))
        self.assertIsNot(actor.process_consumer_queue, Queue("some_other_name_2"))
        self.assertIs(actor.process_consumer_queue, queue)
        self.assertEqual(actor.process_consumer_timeout, None)
        self.assertEqual(actor.process_consumer_raise_on_empty, True)

        #test not ensure_empty qsize = 0
        actor = MockedActor('actor')
        actor._Actor__process_consumer_event = actor.mock_process_consumer_event
        actor._Actor__loop = False
        queue = Queue('queue_name')

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.process_consumer_function, None)
        self.assertEqual(actor.process_consumer_queue, None)
        self.assertEqual(actor.process_consumer_timeout, None)
        self.assertEqual(actor.process_consumer_raise_on_empty, None)

        actor._Actor__consumer(function="some function", queue=queue, timeout=5, ensure_empty=False)

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.process_consumer_function, None)
        self.assertEqual(actor.process_consumer_queue, None)
        self.assertEqual(actor.process_consumer_timeout, None)
        self.assertEqual(actor.process_consumer_raise_on_empty, None)

        #test not ensure_empty qsize > 0
        actor = MockedActor('actor')
        actor._Actor__process_consumer_event = actor.mock_process_consumer_event
        actor._Actor__loop = False
        queue = Queue('queue_name')

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.process_consumer_function, None)
        self.assertEqual(actor.process_consumer_queue, None)
        self.assertEqual(actor.process_consumer_timeout, None)
        self.assertEqual(actor.process_consumer_raise_on_empty, None)

        queue.put("some_event")

        self.assertEqual(queue._Queue__has_content.ready(), True)
        self.assertEqual(queue.qsize(), 1)

        actor._Actor__consumer(function="some function", queue=queue, timeout=5, ensure_empty=False)

        self.assertEqual(queue._Queue__has_content.ready(), True)
        self.assertEqual(queue.qsize(), 1)
        self.assertEqual(actor.process_consumer_function, None)
        self.assertEqual(actor.process_consumer_queue, None)
        self.assertEqual(actor.process_consumer_timeout, None)
        self.assertEqual(actor.process_consumer_raise_on_empty, None)

        #test raise error
        actor = MockedActor('actor')
        actor._Actor__process_consumer_event = actor.mock_process_consumer_event_alt
        actor.raise_error = AttributeError
        actor._Actor__loop = False
        queue = Queue('queue_name')
        queue.put("some_event")

        self.assertEqual(queue._Queue__has_content.ready(), True)
        self.assertEqual(queue.qsize(), 1)

        with self.assertRaises(AttributeError):
            actor._Actor__consumer(function="some function", queue=queue, ensure_empty=True)
        actor.raise_error = QueueEmpty
        actor._Actor__consumer(function="some function", queue=queue, ensure_empty=True)

    def test_get_queued_event(self):
        #test success no timeout
        actor = MockedActor('actor')
        queue = Queue('queue_name')
        queue.put("some_event")
        event = actor._Actor__get_queued_event(queue=queue)
        self.assertEqual(event, "some_event")

        #test success with timeout
        actor = MockedActor('actor')
        queue = Queue('queue_name')
        actor.threads.spawn(actor.mock_modify_content, queue=queue)
        event = actor._Actor__get_queued_event(queue=queue, timeout=3)
        self.assertIs(event, "mock_event")
        actor.threads.kill()

        #test fail with timeout
        actor = MockedActor('actor')
        queue = Queue('queue_name')
        actor.threads.spawn(actor.mock_modify_content, queue=queue)
        with self.assertRaises(QueueEmpty):
            actor._Actor__get_queued_event(queue=queue, timeout=1)
        actor.threads.kill()

        #test fail no timeout
        actor = MockedActor('actor')
        queue = Queue('queue_name')
        with self.assertRaises(QueueEmpty):
            actor._Actor__get_queued_event(queue=queue)

    def test_process_consumer_event(self):
        #test queue empty
        actor = MockedActor('actor')
        actor._Actor__do_consume = actor.mock_do_consume
        actor._Actor__blocking_consume = True
        queue = MockedQueue('queue_name')

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.did_consume, 0)
        self.assertEqual(len(actor.consumed_events), 0)

        actor._Actor__process_consumer_event(function=None, queue=queue, raise_on_empty=False)

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.did_consume, 0)
        self.assertEqual(len(actor.consumed_events), 0)

        #test queue empty and raise_on_empty = True
        actor = MockedActor('actor')
        actor._Actor__do_consume = actor.mock_do_consume
        actor._Actor__blocking_consume = True
        queue = MockedQueue('queue_name')

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.did_consume, 0)
        self.assertEqual(len(actor.consumed_events), 0)

        with self.assertRaises(QueueEmpty):
            actor._Actor__process_consumer_event(function=None, queue=queue, raise_on_empty=True)

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.did_consume, 0)
        self.assertEqual(len(actor.consumed_events), 0)

        #test blocking consume
        actor = MockedActor('actor')
        actor._Actor__do_consume = actor.mock_do_consume
        actor._Actor__blocking_consume = True
        queue = MockedQueue('queue_name')
        
        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.did_consume, 0)
        self.assertEqual(len(actor.consumed_events), 0)

        queue.put("mock_event_1")
        queue.put("mock_event_2")
        queue.put("mock_event_3")

        self.assertEqual(queue._Queue__has_content.ready(), True)
        self.assertEqual(queue.qsize(), 3)
        self.assertEqual(actor.did_consume, 0)
        self.assertEqual(len(actor.consumed_events), 0)

        actor._Actor__process_consumer_event(function=None, queue=queue)
        actor._Actor__process_consumer_event(function=None, queue=queue)
        actor._Actor__process_consumer_event(function=None, queue=queue)

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.consumed_events[0], "mock_event_1")
        self.assertEqual(actor.consumed_events[1], "mock_event_2")
        self.assertEqual(actor.consumed_events[2], "mock_event_3")
        self.assertEqual(actor.did_consume, 3)
        self.assertEqual(len(actor.consumed_events), 3)

        #test not blocking consume
        actor = MockedActor('actor')
        actor._Actor__do_consume = actor.mock_do_consume
        actor._Actor__blocking_consume = False
        queue = MockedQueue('queue_name')
        
        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.did_consume, 0)
        self.assertEqual(len(actor.consumed_events), 0)

        queue.put("mock_event_1")
        queue.put("mock_event_2")
        queue.put("mock_event_3")

        self.assertEqual(queue._Queue__has_content.ready(), True)
        self.assertEqual(queue.qsize(), 3)
        self.assertEqual(actor.did_consume, 0)
        self.assertEqual(len(actor.consumed_events), 0)

        actor._Actor__process_consumer_event(function=None, queue=queue)
        actor._Actor__process_consumer_event(function=None, queue=queue)
        actor._Actor__process_consumer_event(function=None, queue=queue)

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.did_consume, 0)
        self.assertEqual(len(actor.consumed_events), 0)

        gevent.sleep(0)

        self.assertEqual(queue._Queue__has_content.ready(), False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.consumed_events[0], "mock_event_1")
        self.assertEqual(actor.consumed_events[1], "mock_event_2")
        self.assertEqual(actor.consumed_events[2], "mock_event_3")
        self.assertEqual(actor.did_consume, 3)
        self.assertEqual(len(actor.consumed_events), 3)

    def test_do_consume(self):
        #test event in self.input does not have required attributes
        actor = MockedActor('actor')
        queue = Queue("some_queue")
        actor.REQUIRED_EVENT_ATTRIBUTES = None
        event = Event()
        event_alt = Event()
        self.assertIsInstance(event, actor.input)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(actor.consumed_event, None)
        self.assertEqual(actor.consumed_args, [])
        self.assertEqual(actor.consumed_kwargs, {})
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        self.assertEqual(actor.consumed, True)
        self.assertIs(actor.consumed_event, event)
        self.assertIsNot(actor.consumed_event, event_alt)
        self.assertEqual(actor.consumed_args, ())
        self.assertEqual(actor.consumed_kwargs, {"origin":queue.name, "origin_queue":queue})

        #test event in self.input has required attributes and has missing required attributes
        #test InvalidActorInput
        actor = MockedActor('actor')
        actor.logger = MockLogger()
        queue = Queue("some_queue")
        actor.REQUIRED_EVENT_ATTRIBUTES = ["some_attribute"]
        event = Event()
        event_alt = Event()
        self.assertIsInstance(event, actor.input)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(actor.consumed_event, None)
        self.assertEqual(actor.consumed_args, [])
        self.assertEqual(actor.consumed_kwargs, {})
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(actor.consumed_event, None)
        self.assertEqual(actor.consumed_args, [])
        self.assertEqual(actor.consumed_kwargs, {})
        self.assertEqual(actor.logger.errored, 1)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)

        #test event in self.input has required attributes but no missing required attributes
        actor = MockedActor('actor')
        actor.logger = MockLogger()
        queue = Queue("some_queue")
        actor.REQUIRED_EVENT_ATTRIBUTES = ["some_attribute"]
        event = Event()
        event.set("some_attribute", True)
        event_alt = Event()
        self.assertIsInstance(event, actor.input)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(actor.consumed_event, None)
        self.assertEqual(actor.consumed_args, [])
        self.assertEqual(actor.consumed_kwargs, {})
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertEqual(actor.consumed, True)
        self.assertIs(actor.consumed_event, event)
        self.assertEqual(actor.consumed_event.some_attribute, True)
        self.assertIsNot(actor.consumed_event, event_alt)
        self.assertEqual(actor.consumed_args, ())
        self.assertEqual(actor.consumed_kwargs, {"origin":queue.name, "origin_queue":queue})

        #test event not in self.input does not have required attributes
        actor = MockedActor('actor')
        actor.logger = MockLogger()
        queue = Queue("some_queue")
        actor.input = (SubSubEvent,)
        event = SubEvent()
        event.convert = event.mock_convert
        event_alt = SubEvent()
        self.assertNotIsInstance(event, actor.input)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(actor.consumed_event, None)
        self.assertEqual(event.converted, False)
        self.assertEqual(actor.consumed_args, [])
        self.assertEqual(actor.consumed_kwargs, {})
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 1)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertEqual(actor.consumed, True)
        self.assertIs(actor.consumed_event, event)
        self.assertEqual(actor.consumed_event.converted, True)
        self.assertIsNot(actor.consumed_event, event_alt)
        self.assertEqual(actor.consumed_args, ())
        self.assertEqual(actor.consumed_kwargs, {"origin":queue.name, "origin_queue":queue})

        #test event not in self.input has required attributes and has missing required attributes
        #test InvalidActorInput 2
        actor = MockedActor('actor')
        actor.logger = MockLogger()
        queue = Queue("some_queue")
        actor.REQUIRED_EVENT_ATTRIBUTES = ["some_attribute"]
        actor.input = (SubSubEvent,)
        event = SubEvent()
        event.convert = event.mock_convert
        event_alt = SubEvent()
        self.assertNotIsInstance(event, actor.input)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(actor.consumed_event, None)
        self.assertEqual(event.converted, False)
        self.assertEqual(actor.consumed_args, [])
        self.assertEqual(actor.consumed_kwargs, {})
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        self.assertEqual(actor.logger.errored, 1)
        self.assertEqual(actor.logger.warned, 1)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(actor.consumed_event, None)
        self.assertEqual(actor.consumed_args, [])
        self.assertEqual(actor.consumed_kwargs, {})

        #test event not in self.input has required attributes but no missing required attributes
        actor = MockedActor('actor')
        actor.logger = MockLogger()
        queue = Queue("some_queue")
        actor.REQUIRED_EVENT_ATTRIBUTES = ["some_attribute"]
        actor.input = (SubSubEvent,)
        event = SubEvent()
        event.set("some_attribute", True)
        event.convert = event.mock_convert
        event_alt = SubEvent()
        self.assertNotIsInstance(event, actor.input)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(actor.consumed_event, None)
        self.assertEqual(event.converted, False)
        self.assertEqual(actor.consumed_args, [])
        self.assertEqual(actor.consumed_kwargs, {})
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 1)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertEqual(actor.consumed, True)
        self.assertIs(actor.consumed_event, event)
        self.assertEqual(actor.consumed_event.converted, True)
        self.assertIsNot(actor.consumed_event, event_alt)
        self.assertEqual(actor.consumed_args, ())
        self.assertEqual(actor.consumed_kwargs, {"origin":queue.name, "origin_queue":queue})

        #test QueueFull
        actor = MockedActor('actor')
        actor.consume = actor.consume_alt
        actor.logger = MockLogger()
        actor.dest_queue = Queue("dest_queue", maxsize=1)
        actor.dest_queue.put("some_dest_event")
        queue = Queue("some_queue")
        event = Event()
        self.assertIsInstance(event, actor.input)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(actor.consumed_event, None)
        self.assertEqual(actor.consumed_args, [])
        self.assertEqual(actor.consumed_kwargs, {})
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.dest_queue.qsize(), 1)
        self.assertEqual(actor.dest_queue.maxsize, 1)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        actor.threads.spawn(actor.mock_modify_content, queue=actor.dest_queue, put_event=False, pull_event=True)
        start = time.time()
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        end = time.time()
        dif = end - start
        self.assertEqual(actor.consumed, False)
        self.assertEqual(actor.consumed_event, None)
        self.assertEqual(actor.consumed_args, [])
        self.assertEqual(actor.consumed_kwargs, {})
        self.assertEqual(queue.qsize(), 1)
        self.assertEqual(actor.dest_queue.qsize(), 0)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertGreater(dif, 1)
        self.assertGreater(3, dif)

        #test InvalidEventConversion
        actor = MockedActor('actor')
        actor.logger = MockLogger()
        queue = Queue("some_queue")
        actor.input = (MockEvent,)
        event = SubEvent()
        event.raise_invalid = True
        event.convert = event.mock_convert
        self.assertNotIsInstance(event, actor.input)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(actor.logger.errored, 1)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)

        #test Exception with rescue and less than max_rescue
        actor = MockedActor('actor', rescue=True, max_rescue=2)
        actor.send_error = actor.mock_send_error
        actor.logger = MockLogger()
        queue = Queue("some_queue")
        actor.input = (MockEvent,)
        event = SubEvent()
        event.convert = event.mock_convert
        event.raise_reg_exception = True
        rescue_attribute = Actor._RESCUE_ATTRIBUTE_NAME_TEMPLATE.format(actor=actor.name)
        self.assertNotIsInstance(event, actor.input)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertEqual(event.get(rescue_attribute, 0), 0)
        self.assertEqual(len(actor.send_error_event), 0)
        start = time.time()
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        end = time.time()
        dif = end - start
        self.assertEqual(actor.logger.warned, 1)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(queue.qsize(), 1)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 1)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertEqual(event.get(rescue_attribute, 0), 1)
        self.assertGreater(dif, .5)
        self.assertGreater(1.5, dif)
        self.assertIs(queue.queue[0], event)
        self.assertIs(queue.qsize(), 1)
        self.assertEqual(len(actor.send_error_event), 0)
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        end = time.time()
        dif = end - start
        self.assertEqual(actor.consumed, False)
        self.assertEqual(queue.qsize(), 2)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 2)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertEqual(event.get(rescue_attribute, 0), 2)    
        self.assertGreater(dif, 1.5)
        self.assertGreater(2.5, dif)  
        self.assertIs(queue.queue[1], event)
        self.assertIs(queue.qsize(), 2)
        self.assertEqual(len(actor.send_error_event), 0)

        #test Exception with rescue and greater than max_rescue
        self.assertEqual(event.get("error", None), None)
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        end = time.time()
        dif = end - start
        self.assertEqual(actor.consumed, False)
        self.assertEqual(queue.qsize(), 2)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 3)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertEqual(event.get(rescue_attribute, 0), 2)    
        self.assertGreater(dif, 1.5)
        self.assertGreater(2.5, dif)  
        self.assertEqual(len(actor.send_error_event), 1)
        self.assertIs(event, actor.send_error_event[0])
        self.assertNotEqual(actor.send_error_event[0].get("error", None), None)

        #test Exception without rescue and less than max_rescue
        actor = MockedActor('actor', rescue=False, max_rescue=1)
        actor.send_error = actor.mock_send_error
        actor.logger = MockLogger()
        queue = Queue("some_queue")
        actor.input = (MockEvent,)
        event = SubEvent()
        event.convert = event.mock_convert
        event.raise_reg_exception = True
        rescue_attribute = Actor._RESCUE_ATTRIBUTE_NAME_TEMPLATE.format(actor=actor.name)
        self.assertNotIsInstance(event, actor.input)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertEqual(event.get(rescue_attribute, 0), 0)
        self.assertEqual(len(actor.send_error_event), 0)
        self.assertEqual(event.get("error", None), None)
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 1)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertEqual(event.get(rescue_attribute, 0), 0)    
        self.assertEqual(len(actor.send_error_event), 1)
        self.assertIs(event, actor.send_error_event[0])
        self.assertNotEqual(actor.send_error_event[0].get("error", None), None)

        #test Exception without rescue and greater than max_rescue
        actor = MockedActor('actor', rescue=False, max_rescue=1)
        actor.send_error = actor.mock_send_error
        actor.logger = MockLogger()
        queue = Queue("some_queue")
        actor.input = (MockEvent,)
        event = SubEvent()
        event.convert = event.mock_convert
        event.raise_reg_exception = True
        rescue_attribute = Actor._RESCUE_ATTRIBUTE_NAME_TEMPLATE.format(actor=actor.name)
        setattr(event, rescue_attribute, 3)
        self.assertNotIsInstance(event, actor.input)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 0)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertEqual(event.get(rescue_attribute, 0), 3)
        self.assertEqual(len(actor.send_error_event), 0)
        self.assertEqual(event.get("error", None), None)
        actor._Actor__do_consume(function=actor.consume, event=event, queue=queue)
        self.assertEqual(actor.consumed, False)
        self.assertEqual(queue.qsize(), 0)
        self.assertEqual(actor.logger.errored, 0)
        self.assertEqual(actor.logger.warned, 1)
        self.assertEqual(actor.logger.infoed, 0)
        self.assertEqual(actor.logger.debuged, 0)
        self.assertEqual(event.get(rescue_attribute, 0), 3)    
        self.assertEqual(len(actor.send_error_event), 1)
        self.assertIs(event, actor.send_error_event[0])
        self.assertNotEqual(actor.send_error_event[0].get("error", None), None)

    def test_create_event(self):
        actor = MockedActor('actor')

        #test multiple output types
        actor.output = (Event, Event)
        with self.assertRaises(ValueError):
            actor.create_event()

        #test missing output types
        actor.output = ()
        with self.assertRaises(ValueError):
            actor.create_event()

        #test success
        actor.output = (Event,)
        event = actor.create_event()
        self.assertIsInstance(event, Event)

    def test_consume(self):
        #test abstractness of consume function
        with self.assertRaises(TypeError):
            Actor('actor')

        class ConsumeActor(Actor):
            def consume(self, event, *args, **kwargs):
                pass

        ConsumeActor('actor')
