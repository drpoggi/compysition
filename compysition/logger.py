#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
#  logging.py
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

import logging

from compysition.queue import _InternalQueuePool
from compysition.event import LogEvent
from compysition.errors import QueueFull
from compysition.util import iterkeys

class Logger(object):

    """**Generates Compysition formatted log messages following the python priority definition to a pool of queues**

    We use a pool in order to support multiple logging types per process. For example, sending to a third party log
    aggregator as WELL as using a filelogger

    Args:
        - name(str):
            | The name to use when sending log events
        - queue_pool(_InternalQueuePool):
            | The pool to use when sending log events
    """

    def __init__(self, name, queue_pool):
        self.name = name
        if not isinstance(queue_pool, _InternalQueuePool):
            raise TypeError("Logger queue_pool must be of type '_InternalQueuePool'")

        self.__pool = queue_pool

    def log(self, level, message, event=None, log_entry_id=None):
        """
        Uses log_entry_id explicitely as the logged ID, if defined. Otherwise, will attempt to ascertain the ID from 'event', if passed
        """
        if not log_entry_id:
            if event:
                log_entry_id = event.meta_id

        for key in iterkeys(self.__pool):
            try:
                log_event = LogEvent(level, self.name, message, id=log_entry_id)
                self.__pool[key].put(log_event)
            except QueueFull:
                self.__pool.wait_until_free()
                self.__pool[key].put(log_event)

    def critical(self, message, event=None, log_entry_id=None):
        """Generates a log message with priority logging.CRITICAL
        """
        self.log(logging.CRITICAL, message, event=event, log_entry_id=log_entry_id)

    def error(self, message, event=None, log_entry_id=None):
        """Generates a log message with priority error(3).
        """
        self.log(logging.ERROR, message, event=event, log_entry_id=log_entry_id)

    def warn(self, message, event=None, log_entry_id=None):
        """Generates a log message with priority logging.WARN
        """
        self.log(logging.WARN, message, event=event, log_entry_id=log_entry_id)
    warning=warn

    def info(self, message, event=None, log_entry_id=None):
        """Generates a log message with priority logging.INFO.
        """
        self.log(logging.INFO, message, event=event, log_entry_id=log_entry_id)

    def debug(self, message, event=None, log_entry_id=None):
        """Generates a log message with priority logging.DEBUG
        """
        self.log(logging.DEBUG, message, event=event, log_entry_id=log_entry_id)