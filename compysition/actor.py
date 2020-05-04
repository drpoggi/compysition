#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  setup.py
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

import traceback
import abc

from gevent import sleep
from gevent.event import Event as GEvent
from copy import deepcopy

from compysition.queue import QueuePool
from compysition.logger import Logger
from compysition.errors import (QueueConnected, InvalidActorOutput, QueueEmpty, InvalidEventConversion, 
    InvalidActorInput, QueueFull)
from compysition.restartlet import RestartPool
from compysition.event import Event
from compysition.util import ignore

class Actor(object):
    """
    The actor class is the abstract base class for all implementing compysition actors.
    In order to be a valid 'module' and connectable with the compysition event flow, a module must be an extension of this class.

    The Actor is responsible for putting events on outbox queues, and consuming incoming events on inbound queues.
    """

    __metaclass__ = abc.ABCMeta

    DEFAULT_EVENT_SERVICE = "default"
    input = Event
    output = Event
    REQUIRED_EVENT_ATTRIBUTES = None

    _async_class = GEvent
    _RESCUE_ATTRIBUTE_NAME_TEMPLATE = "{actor}_rescue_num"

    def __init__(self,
            name,
            size=0,
            blocking_consume=False,
            rescue=False,
            max_rescue=5,
            convert_output=False,
            *args,
            **kwargs):
        """
        **Base class for all compysition actors**

        Parameters:

            name (str):
                | The instance name
            size (Optional[int]):
                | The max amount of events any outbound queue connected to this actor may contain. A value of 0 represents an infinite qsize
                | (Default: 0)
            blocking_consume (Optional[bool]):
                | Define if this module should spawn a greenlet for every single 'consume' execution, or if
                | it should execute 'consume' and block until that 'consume' is complete. This is usually
                | only necessary if executing work on an event in the order that it was received is critical.
                | (Default: False)

        """
        self.blockdiag_config = {"shape": "box"}
        self.name = name
        self.size = size
        self.pool = QueuePool(size)
        self.logger = Logger(name, self.pool.logs)
        self.__loop = True
        self.threads = RestartPool(logger=self.logger, sleep_interval=1)

        self.__run = self._async_class()
        self.__block = self._async_class()
        self._clear_all()
        self.__blocking_consume = blocking_consume
        self.rescue = rescue
        self.max_rescue = max_rescue

        self.convert_output = convert_output

    def _clear_all(self):
        self.__run.clear()
        self.__block.clear()

    def block(self):
        self.__block.wait()

    def connect_error_queue(self, destination_queue_name="inbox", *args, **kwargs):
        self.__connect_queue(pool_scope=self.pool.error, destination_queue_name="error_{0}".format(destination_queue_name), *args, **kwargs)

    def connect_log_queue(self, destination_queue_name="inbox", *args, **kwargs):
        self.__connect_queue(pool_scope=self.pool.logs, destination_queue_name="log_{0}".format(destination_queue_name), *args, **kwargs)

    def connect_queue(self, *args, **kwargs):
        self.__connect_queue(pool_scope=self.pool.outbound, *args, **kwargs)

    def __connect_queue(self, source_queue_name="outbox", destination=None, destination_queue_name="inbox", pool_scope=None, check_existing=True):
        """Connects the <source_queue_name> queue to the <destination> queue.
        If the destination queue already exists, the source queue is changed to be a reference to that queue, as Many to One connections
        are supported, but One to Many is not"""

        source_queue = pool_scope.get(source_queue_name, None)
        destination_queue = destination.pool.inbound.get(destination_queue_name, None)

        if check_existing:
            #this should not be optional.  Ignoring theses checks can really cause issues (s.a. infinite loops)
            if source_queue is not None:
                raise QueueConnected("Outbound queue {queue_name} on {source_name} is already connected".format(queue_name=source_queue_name, source_name=self.name))
            if destination_queue is not None:
                raise QueueConnected("Inbound queue {queue_name} on {destination_name} is already connected".format(queue_name=destination_queue_name, destination_name=destination.name))

        if source_queue is None:
            if destination_queue is None:
                source_queue = pool_scope.add(source_queue_name)
                destination.register_consumer(destination_queue_name, source_queue)
            else:
                pool_scope.add(source_queue_name, queue=destination_queue)

        else:
            if destination_queue is None:
                destination.register_consumer(destination_queue_name, source_queue)
            else:
                #dumping into self can create an infinite loop
                assert source_queue is not destination_queue
                source_queue.dump(destination_queue)
                pool_scope.add(destination_queue.name, queue=destination_queue)

        self.logger.info("Connected queue '{0}' to '{1}.{2}'".format(source_queue_name, destination.name, destination_queue_name))

    def loop(self):
        '''
        The global lock for this module
        '''
        return self.__loop

    def is_running(self):
        return self.__run.is_set()

    def register_consumer(self, queue_name, queue):
        '''
        Add the passed queue and queue name to
        '''
        self.pool.inbound.add(queue_name, queue=queue)
        self.threads.spawn(self.__consumer, self.consume, queue)

    def ensure_tuple(self, data):
        if not isinstance(data, tuple):
            if isinstance(data, list):
                return tuple(data)
            else:
                return (data, )
        return data

    def start(self):
        '''Starts the module.'''

        self.input = self.ensure_tuple(data=self.input)
        self.output = self.ensure_tuple(data=self.output)

        with ignore(AttributeError):
            self.logger.debug("searching for pre_hook()")
            self.pre_hook()
            self.logger.debug("pre_hook() found, and excuted")

        self.__run.set()
        self.logger.debug("Started with max queue size of {size} events".format(size=self.size))

    def stop(self):
        '''Stops the loop lock and waits until all registered consumers have exit.'''

        self.__loop = False
        self.__block.set()

        # This should do a self.threads.join() but currently it is blocking. This issue needs to be resolved
        # But in the meantime post_hook will execute

        with ignore(AttributeError):
            self.logger.debug("searching for post_hook()")
            self.post_hook()
            self.logger.debug("post_hook() found, and executed")

    def send_event(self, event, queues=None, check_output=True):
        """
        Sends event to all registered outbox queues. If multiple queues are consuming the event,
        a deepcopy of the event is sent instead of raw event.
        """

        if not queues:
            queues = self.pool.outbound

        self._loop_send(event, queues, check_output)

    def send_error(self, event):
        """
        Calls 'send_event' with all error queues as the 'queues' parameter
        """
        self._loop_send(event, queues=self.pool.error, check_output=False)

    def _loop_send(self, event, queues, check_output=True):
        """
        :param event:
        :param queues:
        :return:
        """
        if check_output and not isinstance(event, self.output):
            raise_error = True
            if self.convert_output:
                raise_error = False
                try:
                    if not isinstance(event, self.output):
                        new_event = event.convert(self.output[0])
                        self.logger.warning("Outgoing event was of type '{_type}' when type {output} was expected. Converted to {converted}".format(
                            _type=type(event), output=self.output, converted=type(new_event)), event=event)
                        event = new_event
                except InvalidEventConversion:
                    #not reachable
                    raise_error = True
            if raise_error:
                raise InvalidActorOutput("Event was of type '{_type}', expected '{output}'".format(_type=type(event), output=self.output))
        try:
            for queue in queues.itervalues():
                self._send(queue, deepcopy(event))
        except AttributeError:
            for queue in queues:
                self._send(queue, deepcopy(event))

    def _send(self, queue, event):
        queue.put(event)
        sleep(0)

    def __consumer(self, function, queue, timeout=10):
        '''Greenthread which applies <function> to each element from <queue>
        '''

        self.__run.wait()

        while self.loop():
            queue.wait_until_content()
            self.__process_consumer_event(function=function, queue=queue, timeout=timeout)

        with ignore(QueueEmpty):
            while queue.qsize() > 0:
                self.__process_consumer_event(function=function, queue=queue, raise_on_empty=True)

    def __process_consumer_event(self, function, queue, timeout=None, raise_on_empty=False):
        try:
            event = self.__get_queued_event(queue=queue, timeout=timeout)
        except QueueEmpty as err:
            #not reachable
            if raise_on_empty:
                raise err
        else:
            if self.__blocking_consume:
                #is there a preferred use case for this over the alternative?
                self.__do_consume(function, event, queue)
            else:
                self.threads.spawn(self.__do_consume, function, event, queue, restart=False)

    def __get_queued_event(self, queue, timeout=None):
        if timeout:
            return queue.get(block=True, timeout=timeout)
        return queue.get()

    def __do_consume(self, function, event, queue):
        """
        A function designed to be spun up in a greenlet to maximize concurrency for the __consumer method
        This function actually calls the consume function for the actor
        """
        try:

            if not isinstance(event, self.input):
                new_event = event.convert(self.input[0])
                self.logger.warning("Incoming event was of type '{_type}' when type {input} was expected. Converted to {converted}".format(
                    _type=type(event), input=self.input, converted=type(new_event)), event=event)
                event = new_event

            if self.REQUIRED_EVENT_ATTRIBUTES:
                missing = [attribute for attribute in self.REQUIRED_EVENT_ATTRIBUTES if not event.get(attribute, None)]
                if len(missing) > 0:
                    raise InvalidActorInput("Required incoming event attributes were missing: {missing}".format(missing=missing))

            try:
                function(event, origin=queue.name, origin_queue=queue)
            except QueueFull as err:
                #not reachable
                err.queue.wait_until_free() # potential TypeError if target queue is not sent
                queue.put(event) # puts event back into origin queue
        except InvalidActorInput as error:
            self.logger.error("Invalid input detected: {0}".format(error))
        except InvalidEventConversion:
            #not reachable
            self.logger.error("Event was of type '{_type}', expected '{input}'".format(_type=type(event), input=self.input))
        except Exception as err:
            self.logger.warning("Event exception caught: {traceback}".format(traceback=traceback.format_exc()), event=event)
            rescue_attribute = Actor._RESCUE_ATTRIBUTE_NAME_TEMPLATE.format(actor=self.name)
            rescue_attempts =  event.get(rescue_attribute, 0)
            if self.rescue and rescue_attempts < self.max_rescue:
                setattr(event, rescue_attribute, rescue_attempts + 1)
                sleep(1)
                queue.put(event)
            else:
                event.error = err
                self.send_error(event)

    def create_event(self, *args, **kwargs):
        try:
            self.output[1]
        except IndexError:
            try:
                return self.output[0](**kwargs)
            except IndexError:
                raise ValueError("Unable to call create_event function without an output type defined")
        else:
            raise ValueError("Unable to call create_event function with multiple output types defined")
            
    @abc.abstractmethod
    def consume(self, event, *args, **kwargs):
        """
        Args:
            event:  The implementation of event.Event this actor is consuming
            *args:
            **kwargs:
        """
        pass