import unittest
import abc
import gevent
import time

from gevent.event import Event as GEvent
from contextlib import contextmanager

from compysition.actor import Actor
from compysition.event import Event, XMLEvent
from compysition.queue import QueuePool, Queue
from compysition.logger import Logger
from compysition.restartlet import RestartPool
from compysition.errors import (QueueConnected, InvalidActorOutput, QueueEmpty, InvalidEventConversion, 
    InvalidActorInput, QueueFull, InvalidEventDataModification)

class MockActor(Actor):
    def consume(self, *args, **kwargs):
        pass

class MockTimeoutException(Exception):
    pass

class TestActor(unittest.TestCase):

    def _assert_timeout(self, func, *args, **kwargs):
        from gevent.event import Event as GEvent
        event = GEvent()
        event.clear()
        def func_wrapper(*args, **kwargs):
            func(*args, **kwargs)
            event.set()
        g = gevent.spawn(func_wrapper, *args, **kwargs)
        assert not event.wait(0.05)

    def test_abstract(self):
        with self.assertRaises(TypeError):
            Actor('actor')
        MockActor('actor')

    def test_init(self):
        with self.assertRaises(TypeError):
            MockActor()
        assert "test" == MockActor("test").name

    def test_block(self):
        a = MockActor('actor')
        self._assert_timeout(a.block) #I don't think this should block if the actor hasn't started
        a.start()
        self._assert_timeout(a.block)
        a.stop()
        a.block()

    def test_is_running(self):
        a = MockActor('actor')
        assert not a.is_running()
        a.start()
        assert a.is_running()
        a.stop()
        assert a.is_running() # I think this should be off/not set

    def _test_single_connect_queue(self, func_name, func_kwargs={}, src_lens={}, dest_lens={}, queue_names={'src':'outbound.', 'dest':'inbound.'}, src=None, dest=None, **kwargs):
        src_actor = MockActor('source_name') if src is None else src
        dest_actor = MockActor('destination_name') if dest is None else dest
        
        src_threads, dest_threads = len(src_actor.threads), len(dest_actor.threads)
        src_pool, src_queue = queue_names['src'].split('.',1)
        dest_pool, dest_queue = queue_names['dest'].split('.',1)
        queue_exists = getattr(dest_actor.pool, dest_pool).get(dest_queue, None) is not None

        func_kwargs = dict({'destination': dest_actor}, **func_kwargs)
        default_queues = {"error": 0, "inbound":0, "outbound": 0, "logs": 1}

        #baseline
        if src is None and dest is None:
            for actor in (src_actor, dest_actor):
                for pool, len_ in default_queues.iteritems():
                    assert len(getattr(actor.pool, pool)) == len_
        #connect
        getattr(src_actor, func_name)(**func_kwargs)
        #validation
        src_lens, dest_lens = dict(default_queues, **src_lens), dict(default_queues, **dest_lens)
        for pool, len_ in src_lens.iteritems():
            assert len(getattr(src_actor.pool, pool)) == len_
        for pool, len_ in dest_lens.iteritems():
            assert len(getattr(dest_actor.pool, pool)) == len_
        assert getattr(src_actor.pool, src_pool)[src_queue] is getattr(dest_actor.pool, dest_pool)[dest_queue]
        assert isinstance(getattr(src_actor.pool, src_pool)[src_queue], Queue)
        assert len(dest_actor.threads) == dest_threads + (1 if not queue_exists else 0)
        assert len(src_actor.threads) == src_threads

        return src_actor, dest_actor

    def test_connect_error_queue(self):
        self._test_connect_queue(func_name='connect_error_queue', pool_name='error', prefix='error_')

    def test_connect_queue(self):
        self._test_connect_queue(func_name='connect_queue', pool_name='outbound', prefix='')

    def test_connect_log_queue(self):
        self._test_connect_queue(func_name='connect_log_queue', pool_name='logs', prefix='log_')

    def _test_connect_queue(self, func_name, pool_name, prefix):
        #test default destination queue name
        src_, dest_ = self._test_single_connect_queue(func_name=func_name,
            func_kwargs={},
            src_lens={pool_name: 1},
            dest_lens={'inbound': 1},
            queue_names={'src': '{}.outbox'.format(pool_name), 'dest': 'inbound.{}inbox'.format(prefix)})

        #test check existing queues
        with self.assertRaises(QueueConnected):
            self._test_single_connect_queue(func_name=func_name, src=src_)
        with self.assertRaises(QueueConnected):
            self._test_single_connect_queue(func_name=func_name, dest=dest_)

        #test missing destination
        with self.assertRaises(AttributeError):
            src_.connect_error_queue()

        #missing src, dest
        src, dest = self._test_single_connect_queue(func_name=func_name,
            func_kwargs={'source_queue_name': 'src_name', 'destination_queue_name': 'dest_name'},
            src_lens={pool_name: 1},
            dest_lens={'inbound': 1},
            queue_names={'src': '{}.src_name'.format(pool_name), 'dest': 'inbound.{}dest_name'.format(prefix)})

        #missing src
        src, dest = self._test_single_connect_queue(func_name=func_name,
            func_kwargs={'source_queue_name': 'src_name2', 'destination_queue_name': 'dest_name', 'check_existing': False},
            src_lens={pool_name: 2},
            dest_lens={'inbound': 1},
            queue_names={'src': '{}.src_name2'.format(pool_name), 'dest': 'inbound.{}dest_name'.format(prefix)},
            src=src, dest=dest)

        #missing dest
        src, dest = self._test_single_connect_queue(func_name=func_name,
            func_kwargs={'source_queue_name': 'src_name2', 'destination_queue_name': 'dest_name2', 'check_existing': False},
            src_lens={pool_name: 2},
            dest_lens={'inbound': 2},
            queue_names={'src': '{}.src_name'.format(pool_name), 'dest': 'inbound.{}dest_name2'.format(prefix)},
            src=src, dest=dest)

        #not missing
        with self.assertRaises(AssertionError):
            src, dest = self._test_single_connect_queue(func_name=func_name,
                func_kwargs={'source_queue_name': 'src_name2', 'destination_queue_name': 'dest_name2', 'check_existing': False},
                src_lens={pool_name: 2},
                dest_lens={'inbound': 2},
                queue_names={'src': '{}.src_name2'.format(pool_name), 'dest': 'inbound.{}dest_name2'.format(prefix)},
                src=src, dest=dest)

    def test_loop(self):
        actor = MockActor('actor')
        assert actor.loop() #I don't think this flag should be set until actor is started
        actor.start()
        assert actor.loop()
        actor.stop()
        assert not actor.loop()
        actor.start()
        assert not actor.loop() #I think we should support restarting an actor

    def test_register_consumer(self):
        actor = MockActor('actor')
        self.assertEqual(len(actor.pool.inbound), 0)
        self.assertEqual(len(actor.threads), 0)
        actor.register_consumer(queue_name="test_name", queue=Queue("test_queue"))
        self.assertEqual(len(actor.pool.inbound), 1)
        self.assertEqual(len(actor.threads), 1)

    def test_ensure_tuple(self):
        actor = MockActor('actor')

        #test data not tuple is list
        data = actor.ensure_tuple(data=[Event])
        assert data == (Event, )

        #test data not tuple is other
        data = actor.ensure_tuple(data=Event)
        assert data == (Event, )

        #test data is tuple
        data = actor.ensure_tuple(data=(Event, ))
        assert data == (Event, )

    def test_start_tuplify(self):
        class ListIO(MockActor):
            input, output = ['a', 'b'], ['c', 'd']
        class TupleIO(MockActor):
            input, output = ('a', 'b'), ('c', 'd')
        class MockIO(MockActor):
            input, output = 'a', 'c'

        actor = ListIO('actor')
        actor.start()
        assert actor.input == ('a', 'b') and actor.output == ('c', 'd')

        actor = TupleIO('actor')
        actor.start()
        assert actor.input == ('a', 'b') and actor.output == ('c', 'd')

        actor = MockIO('actor')
        actor.start()
        assert actor.input == ('a',) and actor.output == ('c',)

    def test_start_hooks(self):
        class HookActor(MockActor):
            pre_hook_ = False
            def pre_hook(self):
                self.pre_hook_ = True

        #test no hooks
        actor = MockActor('actor')
        actor.start()

        #test hooks
        actor = HookActor('actor')
        actor.start()
        assert actor.pre_hook_

    def test_start_consumers(self):
        class SendActor(Actor):
            consumed = 0
            def consume(self, event, *args, **kwargs):
                self.consumed += 1

        actor = SendActor('actor')
        actor.register_consumer('in', Queue('in'))
        assert actor.consumed == 0
        gevent.sleep(0.01)
        assert actor.consumed == 0
        actor.pool.inbound['in'].put(Event())
        actor.pool.inbound['in'].put(Event())
        gevent.sleep(0.01)
        assert actor.consumed == 0
        actor.start()
        gevent.sleep(0.01)
        assert actor.consumed == 2
        actor.pool.inbound['in'].put(Event())
        gevent.sleep(0.01)
        assert actor.consumed == 3
        actor.stop()

    def test_stop_hooks(self):
        class HookActor(MockActor):
            post_hook_ = False
            def post_hook(self):
                self.post_hook_ = True

        #test no hooks
        actor = MockActor('actor')
        actor.stop()

        #test hooks
        actor = HookActor('actor')
        actor.stop()
        assert actor.post_hook_

    def test_stop_consumers(self):
        class SendActor(Actor):
            consumed = 0
            def consume(self, event, *args, **kwargs):
                self.consumed += 1

        actor = SendActor('actor')
        actor.register_consumer('in', Queue('in'))
        actor.pool.inbound['in'].put(Event())
        actor.pool.inbound['in'].put(Event())
        actor.start()
        actor.stop()
        gevent.sleep(0.01)
        assert actor.consumed == 2
        actor.pool.inbound['in'].put(Event())
        gevent.sleep(0.01)
        assert actor.consumed == 2

    @contextmanager
    def _setup_actor(self, class_, *args, **kwargs):
        a = class_('actor', *args, **kwargs)
        a.register_consumer('in', Queue('in'))
        a.pool.error.add('error')
        a.pool.outbound.add('out1')
        a.pool.outbound.add('out2')
        a.start()
        yield a
        a.stop()

    def _get_event(self, actor, queue_names=tuple(), pool_name='inbound', logs=None, queue_len=1):
        gevent.sleep(0.01)
        for p_name in ('inbound', 'outbound', 'error'):
            for q_name, queue in getattr(actor.pool, p_name).iteritems():
                if p_name == pool_name and q_name in queue_names:
                    assert len(queue) == queue_len
                else:
                    assert len(queue) == 0
        if logs is not None:
            for queue in actor.pool.logs.itervalues():
                assert len(queue) == logs
                for _ in range(len(queue)):
                    queue.get()
        return [q.get() for q_name, q in getattr(actor.pool, pool_name).iteritems() if q_name in queue_names]

    def _test_send_event_actor(self, class_, queue_names, pool_name, mod_func=lambda s, a, e: None, error=None, eq_id=True, logs=None, event_class=Event, event_kwargs={}, *args, **kwargs):
        event = event_class(**event_kwargs)
        with self._setup_actor(class_=class_, *args, **kwargs) as a:
            mod_func(s=self, a=a, e=event)
            a.pool.inbound['in'].put(event)
            n_events = self._get_event(actor=a, queue_names=queue_names, pool_name=pool_name, logs=logs)
            assert len(n_events) == len(queue_names)
            for n_event in n_events:
                assert event.event_id == n_event.event_id if eq_id else event.event_id != n_event.event_id
                assert event is not n_event # I think it'd be nice to not clone when we don't have to (i.e. 1:1 actor relations)
                assert event.error.__class__ == error if error is not None else getattr(event, 'error', None) is None

    def _setattrs(self, obj, **kwargs):
        for k, v in kwargs.iteritems():
            setattr(obj, k, v)

    def test_sending_events(self):
        '''Simple Actor Simulations'''
        class RandomException(Exception): pass
        class SendEventSingle(Actor):
            consume = lambda self, event, *a, **k: self.send_event(event, [self.pool.outbound['out1']])
        class SendEventSingleAlt(Actor):
            consume = lambda self, event, *a, **k: self.send_event(Event(), [self.pool.outbound['out1']])
        class SendEventAll(Actor):
            consume = lambda self, event, *a, **k: self.send_event(event)
        class SendEventError(Actor):
            consume = lambda self, event, *a, **k: self.send_event(event, [self.pool.error['error']])
        class SendError(Actor):
            consume = lambda self, event, *a, **k: self.send_error(event)
        class OutputSuccess(Actor):
            consume = lambda self, event, *a, **k: self.send_event(event, [self.pool.outbound['out1']], check_output=True)
        class OutputError(OutputSuccess):
            output = XMLEvent
        class OutputErrorAlt(SendError):
            output = XMLEvent
        class RaiseActor(Actor):
            def consume(self, event, *args, **kwargs):
                raise RandomException

        #single queue send
        self._test_send_event_actor(class_=SendEventSingle, queue_names=('out1', ), pool_name='outbound', logs=2)
        
        #single queue send with different event
        self._test_send_event_actor(class_=SendEventSingleAlt, queue_names=('out1', ), pool_name='outbound', eq_id=False, logs=2)

        #multi queue send
        self._test_send_event_actor(class_=SendEventAll, queue_names=('out1', 'out2'), pool_name='outbound', logs=2)

        #send to queue in seperate pool
        self._test_send_event_actor(class_=SendEventError, queue_names=('error', ), pool_name='error', logs=2)

        #send error
        self._test_send_event_actor(class_=SendError, queue_names=('error', ), pool_name='error', logs=2)

        #send error multi
        self._test_send_event_actor(class_=SendError, queue_names=('error', 'error2'), pool_name='error', logs=2, mod_func=lambda s, a, e: a.pool.error.add('error2'))

        #valid output conversion
        self._test_send_event_actor(class_=OutputSuccess, queue_names=('out1',), pool_name='outbound', logs=2, convert_output=True)
        self._test_send_event_actor(class_=OutputError, queue_names=('out1', ), pool_name='outbound', logs=3, convert_output=True)

        #invalid output conversion
        self._test_send_event_actor(class_=OutputError, queue_names=('error', ), pool_name='error', logs=3, error=InvalidActorOutput)
        self._test_send_event_actor(class_=OutputError, queue_names=('error', ), pool_name='error', logs=3, error=InvalidEventDataModification, convert_output=True, event_kwargs={"_data": ""})

        #ignore output conversion via sending error
        self._test_send_event_actor(class_=OutputErrorAlt, queue_names=('error', ), pool_name='error', logs=2, convert_output=True)

        #test error in consume
        self._test_send_event_actor(class_=RaiseActor, queue_names=('error', ), pool_name='error', logs=3, error=RandomException)

        #test error in consume with rescue
        event = Event()
        with self._setup_actor(class_=RaiseActor, rescue=True, max_rescue=2) as a:
            a.pool.inbound['in'].put(event)
            self._get_event(actor=a, queue_names=tuple(), pool_name='error', logs=3)
            gevent.sleep(1)
            self._get_event(actor=a, queue_names=tuple(), pool_name='error', logs=1)
            gevent.sleep(1)
            n_events = self._get_event(actor=a, queue_names=('error', ), pool_name='error', logs=1)
            assert len(n_events) == 1
            for n_event in n_events:
                assert event.event_id == n_event.event_id
                assert event is not n_event
                assert event.error.__class__ == RandomException

    def test_process_event(self):
        class Valid(Actor):
            consume = lambda self, event, *args, **kwargs: self.send_event(event, [self.pool.outbound['out1']])
        class InputError(MockActor):
            input = XMLEvent
        class RequiredAttrs(Valid):
            REQUIRED_EVENT_ATTRIBUTES = ('some_option', 'some_option2')

        #valid input
        self._test_send_event_actor(class_=Valid, queue_names=('out1', ), pool_name='outbound', logs=2)

        #invalid input
        self._test_send_event_actor(class_=InputError, queue_names=tuple(), pool_name='outbound', logs=3)

        #valid required events
        self._test_send_event_actor(class_=RequiredAttrs, queue_names=('out1',), pool_name='outbound', logs=2, mod_func=lambda s, a, e: s._setattrs(e, some_option=True, some_option2=True))
        
        #invalid required events due to attr value
        #the check validates against trueness and existance. I believe this is unintended behavior
        self._test_send_event_actor(class_=RequiredAttrs, queue_names=tuple(), pool_name='outbound', logs=3, mod_func=lambda s, a, e: s._setattrs(e, some_option=True, some_option2=False))
        
        #invalid required events
        self._test_send_event_actor(class_=RequiredAttrs, queue_names=tuple(), pool_name='outbound', logs=3, mod_func=lambda s, a, e: s._setattrs(e, some_option=True))

    def test_create_event(self):
        actor = MockActor('actor')

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