#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
#  flowcontroller.py
#
#  Copyright 2014 Adam Fiebig <adam.fiebig@cuanswers.com>
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

from uuid import uuid4 as uuid

from compysition.actor import Actor
from compysition.event import XMLEvent, JSONEvent
from compysition.util import get_uuid

__all__ = [
    "FlowController",
    "ToDict",
    "ToXML"
]

class _Flow(Actor):
    def consume(self, event, *args, **kwargs):
        self.send_event(event)

class FlowController(Actor):
    '''
    Simple module that is designed to accept any input and replicate it to any outbox(s)
    For example, if one were to want to abstract multiple potential data flows to a single aggregator (EventMatcher) inbox, the outbox behind
    this FlowController module would serve as a mask so that the data aggregator isn't waiting for data flow channels that will never arrive

    In the future this could be designed to handle multiple functions, such as controlling rate of event flow through it

    '''

    def __init__(self, name, trigger_errors=False, generate_fresh_ids=False, *args, **kwargs):
        self.trigger_errors = trigger_errors
        self.generate_fresh_ids = generate_fresh_ids
        super(FlowController, self).__init__(name, *args, **kwargs)

    def consume(self, event, *args, **kwargs):
        if self.generate_fresh_ids:
            event._event_id = get_uuid()
            event.meta_id = event._event_id
        if event.error and self.trigger_errors:
            self.send_error(event)
        else:
            self.send_event(event)

class ToDict(_Flow):
    output = JSONEvent

class ToXML(_Flow):
    output = XMLEvent
