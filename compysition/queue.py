#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
#  Copyright 2014 Adam Fiebig <fiebig.adam@gmail.com>
#  Originally based on "wishbone" project by smetj
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
import gevent.queue as gqueue

from uuid import uuid4 as uuid
from gevent import sleep
from gevent.hub import LoopExit
from gevent.event import Event

from compysition.errors import QueueEmpty, QueueFull
from compysition.util import get_uuid

class _InternalQueuePool(dict):
    """
    **A queue pool that handles logic of adding a placeholder Queue until an explicit call to 'add' is made**

    Parameters:
        placeholder (Optional[str]):
            | The name of an optional placeholder queue to add. This is useful in the event that a temporary queue needs
            | to exist to collect events until a consumer is defined
            | Default: None
        size (Optional[int]):
            | The maxsize of each queue in this pool. A value of 0 represents an unlimited size
            | Default: 0
    """

    def __init__(self, placeholder=None, size=None, *args, **kwargs):
        self.__size = size if size is not None and size > 0 else None
        self.placeholder = placeholder
        super(_InternalQueuePool, self).__init__(*args, **kwargs)
        if self.placeholder:
            self[self.placeholder] = Queue(self.placeholder, maxsize=self.__size)

    def add(self, name, queue=None):
        if not queue:
            queue = Queue(name, maxsize=self.__size)

        if self.placeholder:
            if self.get(self.placeholder, None):
                placeholder = self.pop(self.placeholder)
                placeholder.dump(queue)

        self[name] = queue
        return queue


class QueuePool(object):

    def __init__(self, size=None):
        self.__size = size
        self.inbound = _InternalQueuePool(size=size)
        self.outbound = _InternalQueuePool(size=size)
        self.error = _InternalQueuePool(size=size)
        self.logs = _InternalQueuePool(size=size, placeholder=get_uuid())

    @property
    def size(self):
        return self.__size

    def list_all_queues(self):
        return (self.inbound.values() + self.outbound.values() + self.error.values() + self.logs.values())

    def join(self):
        """**Blocks until all queues in the pool are empty.**"""
        for queue in self.list_all_queues():
            queue.wait_until_empty()


class Queue(gqueue.Queue):
        
    '''A subclass of gevent.queue.Queue used to organize communication messaging between Compysition Actors.

    Parameters:

        name (str):
            | The name of this queue. Used in certain actors to determine origin faster than reverse key-value lookup

    '''

    def __init__(self, name, *args, **kwargs):
        super(Queue, self).__init__(*args, **kwargs)
        self.name = name
        self.__has_content = Event()
        self.__has_content.clear()

    def get(self, block=False, *args, **kwargs):
        '''Gets an element from the queue.'''

        try:
            element = super(Queue, self).get(block=block, *args, **kwargs)
        except gqueue.Empty:
            self.__has_content.clear()
            raise QueueEmpty("Queue {0} has no waiting events".format(self.name))

        if self.qsize() == 0:
            self.__has_content.clear()

        return element

    def put(self, element, *args, **kwargs):
        '''Puts element in queue.'''
        try:
            super(Queue, self).put(element, *args, **kwargs)
            self.__has_content.set()
        except gqueue.Full:
            #only if block = False or (block = True and timeout not None)
            raise QueueFull(message="Queue {0} is full".format(self.name), queue=self)

    def wait_until_content(self):
        '''Blocks until at least 1 slot is taken.'''
        self.__has_content.wait()

    def wait_until_empty(self):
        '''Blocks until the queue is completely empty.'''

        while not self.__has_content.is_set():
            sleep(0)

    def wait_until_free(self):
        '''Blocks until the queue has at lease 1 free slot.'''

        while self.qsize() >= self.maxsize:
            sleep(0)
            
    def dump(self, other_queue):
        """**Dump all items on this queue to another queue**"""
        try:
            while True:
                other_queue.put(self.get(block=False))
        except QueueEmpty:
            pass
