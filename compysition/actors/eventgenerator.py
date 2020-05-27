# !/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  testevent.py
#
#  Copyright 2014 Adam Fiebig <fiebig.adam@gmail.com>
#  Originally based on 'wishbone' project by smetj
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 3 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston,
#  MA 02110-1301, USA.
#
#
import gevent

from apscheduler.schedulers.gevent import GeventScheduler

'''
# Can be used to help troubleshoot errors inside the GeventScheduler
import logging

log = logging.getLogger('apscheduler.executors.default')
log.setLevel(logging.INFO)  # DEBUG

fmt = logging.Formatter('%(levelname)s:%(name)s:%(message)s')
h = logging.StreamHandler()
h.setFormatter(fmt)
log.addHandler(h)
'''

from compysition.actor import Actor
from compysition.event import Event
from compysition.actors.util.udplib import UDPInterface
from compysition.util import range_

class EventProducer(Actor):
    '''
    Description:
        Generates a new event upon consuming an event

    Parameters:
        event_class (Optional[compysition.event.Event]):
            | The class that the generated event should be created as
            | Default: Event
        event_kwargs (Optional[int]):
            | Any additional kwargs to add to the event, including data
        generate_error (Optional[bool]):
            | Whether or not to also send the event via Actor.send_error
            | Default: False
    '''
    def __init__(self, name, event_class=Event, event_kwargs=None, generate_error=False, *args, **kwargs):
        super(EventProducer, self).__init__(name, *args, **kwargs)
        self.blockdiag_config["shape"] = "flowchart.input"
        self.generate_error = generate_error
        self.event_kwargs = event_kwargs or {}
        self.output = event_class

    def _do_produce(self):
        event = self.output[0](**self.event_kwargs)
        self.logger.debug("Generated new event {event_id}".format(event_id=event.event_id))
        self.send_event(event)
        if self.generate_error:
            event = self.output[0](**self.event_kwargs)
            self.send_error(event)

    def consume(self, event, *args, **kwargs):
        self._do_produce()

class UDPEventProducer(EventProducer):
    '''
    Description:
        An actor that utilized a UDP interface to coordinate between other UDPEventGenerator actors running on its same subnet to coordinate a master/slave relationship of generating an event with the specified arguments and attributes. Only the master in the 'pool' of registered actors will generate an event at the specified interval
        Links with other producers via UDP generating an event if current prducer is master and consumes an event_class
        TODO: should implement communication upon slave node consuming an event
    '''
    def __init__(self, name, *args, **kwargs):
        super(UDPEventProducer, self).__init__(name, *args, **kwargs)
        self._init_peers_interface(*args, **kwargs)

    def _init_peers_interface(self, service="default", environment_scope='default', peers_interface=None, *args, **kwargs):
        self.peers_interface = peers_interface
        if not self.peers_interface:
            self.peers_interface = UDPInterface("{0}-{1}".format(service, environment_scope), logger=self.logger)

    def pre_hook(self):
        #super(UDPEventProducer, self).pre_hook()
        self.peers_interface.start()

    def _do_produce(self):
        if self.peers_interface.is_master():
            super(UDPEventProducer, self)._do_produce()

class ScheduledEventProducer(EventProducer):
    '''
    Desciption:
        Continuously generates an event based on a defined interval, or if an event is consumed

    Parameters:
        producers (Optional[int]):
            | The number of greenthreads to spawn that each spawn events at the provided interval
            | Default: 1
        interval (Optional[float] OR dict):
            | The interval (in seconds) between each generated event.
            | Should have a value > 0.
            | Can also be a dict, supporting values of weeks, days, hours, minutes, and seconds
            | default: 5
        delay (Optional[float]):
            | The time (in seconds) to wait before initial event generation.
            | Default: 0
        interval_grace_time (Optional[int]):
            | Sometimes the scheduler can fail to wakeup and execute a job right at the set interval. This is how much
            | time (in seconds) the scheduler can miss the interval time by and the job will still be run.
            | Default: None (will use apscheduler's default miss_grace_time of 1 second)
    '''

    '''
    MIXIN Attributes:
        DEFAULT_INTERVAL = {}
        def _parse_interval(self, interval):
        def _initialize_jobs(self):
    '''
    def __init__(self, name, *args, **kwargs):
        super(ScheduledEventProducer, self).__init__(name, *args, **kwargs)
        self._init_scheduler(*args, **kwargs)

    def _init_scheduler(self, producers=1, interval=5, delay=0, scheduler=None, interval_grace_time=None, *args, **kwargs):
        self.interval = self._parse_interval(interval)
        self.delay = delay
        self.producers = producers
        self.scheduler = scheduler
        self.interval_grace_time = interval_grace_time
        if not self.scheduler:
            self.scheduler = GeventScheduler(misfire_grace_time=self.interval_grace_time)

    def pre_hook(self):
        #super(ScheduledEventProducer, self).pre_hook()
        self._initialize_jobs()
        gevent.sleep(self.delay)
        self.scheduler.start()

    def post_hook(self):
        #super(ScheduledEventProducer, self).post_hook()
        self.scheduler.shutdown()

class ScheduledUDPEventProducer(UDPEventProducer, ScheduledEventProducer):
    '''
    Desciption:
        Continuously generates an event based on a defined interval, or if an event is consumed.
        But only if the current UDP node is considered the master.
    '''
    def __init__(self, name, *args, **kwargs):
        ScheduledEventProducer.__init__(self, name, *args, **kwargs)
        UDPEventProducer._init_peers_interface(self, *args, **kwargs)

    def pre_hook(self):
        UDPEventProducer.pre_hook(self)
        ScheduledEventProducer.pre_hook(self)

class CallbackEventProducer(EventProducer):
    def __init__(self, name, is_running=False, *args, **kwargs):
        super(CallbackEventProducer, self).__init__(name, *args, **kwargs)
        self._is_running = is_running

    @property
    def is_running(self):
        return self._is_running

    def _do_produce(self):
        if not self._is_running:
            self._is_running = True
            super(CallbackEventProducer, self)._do_produce()

    def consume(self, event, *args, **kwargs):
        self._is_running = False

class CallbackScheduledEventProducer(CallbackEventProducer, ScheduledEventProducer):
    def __init__(self, name, *args, **kwargs):
        CallbackEventProducer.__init__(self, name, *args, **kwargs)
        ScheduledEventProducer._init_scheduler(self, *args, **kwargs)

class CallbackScheduledUDPEventProducer(CallbackEventProducer, ScheduledUDPEventProducer):
    def __init__(self, name, *args, **kwargs):
        CallbackEventProducer.__init__(self, name, *args, **kwargs)
        ScheduledUDPEventProducer._init_scheduler(self, *args, **kwargs)
        ScheduledUDPEventProducer._init_peers_interface(self, *args, **kwargs)

    def _do_produce(self):
        if not self._is_running:
            self._is_running = True
            super(ScheduledUDPEventProducer, self)._do_produce()

class IntervalSchedulingMixin:
    '''
    Description:
        Template for defining and processing interval schedules
    '''
    DEFAULT_INTERVAL = {'weeks': 0,
                         'days': 0,
                         'hours': 0,
                         'minutes': 0,
                         'seconds': 5}

    def _parse_interval(self, interval):
        _interval = {}
        _interval.update(self.DEFAULT_INTERVAL)

        if isinstance(interval, int):
            _interval['seconds'] = interval
        elif isinstance(interval, dict):
            _interval = {key:interval.get(key, value) for key, value in self.DEFAULT_INTERVAL.items()}

        return _interval

    def _initialize_jobs(self):
        for i in range_(self.producers):
            self.scheduler.add_job(self._do_produce, 'interval', **self.interval)

class CronSchedulingMixin:
    '''
    Description:
        Template for defining and processing cron schedules
        An EventGenerator that supports cron-style scheduling, using the following keywords: year, month, day, week, day_of_week, hour, minute, second. See 'apscheduler' documentation for specifics of configuring those keywords
    '''

    DEFAULT_INTERVAL = {'year': '*',
                        'month': '*',
                        'day': '*',
                        'week': '*',
                        'day_of_week': '*',
                        'hour': '*',
                        'minute': '*',
                        'second': '*/12'}

    def _parse_interval(self, interval):
        _interval = self.DEFAULT_INTERVAL
        if isinstance(interval, dict):
            _interval = {key:str(interval.get(key, value)) for key, value in self.DEFAULT_INTERVAL.items()}
        return _interval

    def _initialize_jobs(self):
        for producer in range_(self.producers):
            self.scheduler.add_job(self._do_produce, 'cron', **self.interval)

class EventGenerator(IntervalSchedulingMixin, ScheduledEventProducer):
    pass

class CallbackEventGenerator(IntervalSchedulingMixin, CallbackScheduledEventProducer):
    pass

class UDPEventGenerator(IntervalSchedulingMixin, ScheduledUDPEventProducer):
    pass

class CallbackUDPEventGenerator(IntervalSchedulingMixin, CallbackScheduledUDPEventProducer):
    pass

class CronEventGenerator(CronSchedulingMixin, ScheduledEventProducer):
    pass
    
class UDPCronEventGenerator(CronSchedulingMixin, ScheduledUDPEventProducer):
    pass
