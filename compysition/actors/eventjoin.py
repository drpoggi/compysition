#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
#  xmlaggregator.py
#
#  Copyright 2014 James Hulett <james.hulett@cuanswers.com>,
#        Adam Fiebig <fiebig.adam@gmail.com>
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

import traceback
import gevent

from time import time
from lxml import etree

from compysition.actor import Actor
from compysition.event import XMLEvent, JSONEvent
from compysition.util import itervalues, iteritems

class MatchedEvent(object):

    def __init__(self, inboxes, key=None):
        self.inboxes_reported = {}
        self.key = key or "joined_root"
        self.created = time()
        if not isinstance(inboxes, list):
            inboxes = [inboxes]

        self.inboxes_reported = {inbox: False for inbox in inboxes}

    def report_inbox(self, inbox_name, data):
        if self.inboxes_reported[inbox_name] == False:
            self.inboxes_reported[inbox_name] = data
        else:
            raise Exception("Inbox {0} already reported for event. Ignoring".format(inbox_name))

    def all_inboxes_reported(self):
        for value in itervalues(self.inboxes_reported):
            if value == False:
                return False
        return True

    @property
    def joined(self):
        return [data for data in itervalues(self.inboxes_reported)]


class MatchedXMLEvent(MatchedEvent):

    @property
    def joined(self):
        root = etree.Element(self.key)
        list(map(lambda xml: root.append(xml), itervalues(self.inboxes_reported)))
        return root


class MatchedJSONEvent(MatchedEvent):

    @property
    def joined(self):
        return {k: v for d in itervalues(self.inboxes_reported) for k, v in iteritems(d)}


class EventJoin(Actor):
    '''**Holds event data until all inbound queues have reported in with events with a matching event_id, then aggregates the data
    and sends it on**

    Parameters:

        name (str):
            | The instance name.
        purge_interval (Optional[int]):
            | If set, determines the interval that events are purged, rather than staying in memory
            | waiting for the other messages. Useful in the event that a certain split event has errored out on
            | one of it's paths to rejoin the main flow. A value of 0 indicates that no purges occur
            | Default: 0

    '''

    matched_event_class = MatchedEvent

    def __init__(self, name, purge_interval=None, *args, **kwargs):
        super(EventJoin, self).__init__(name, *args, **kwargs)
        self.events = {}
        self.key = kwargs.get('key', self.name)
        self.purge_interval = purge_interval

    def pre_hook(self):
        if self.purge_interval and self.purge_interval > 0:
            self.threads.spawn(self.event_purger)

    def event_purger(self):
        while self.loop():
            for key, event in iteritems(self.events):
                if event is not None:
                    purge_time = event.created + self.purge_interval
                    if purge_time < time():
                        del self.events[key]
            gevent.sleep(self.purge_interval / 2)

    def consume(self, event, *args, **kwargs):
        inbox_origin = kwargs.get('origin_queue', None)
        waiting_event = self.events.get(event.event_id, None)
        try:
            if waiting_event:
                waiting_event.report_inbox(inbox_origin, event.data)
                if waiting_event.all_inboxes_reported():
                    event.data = waiting_event.joined
                    self.send_event(event)
                    del self.events[event.event_id]
            else:
                self.events[event.event_id] = self.matched_event_class([q for q in itervalues(self.pool.inbound)], key=self.key)
                self.events.get(event.event_id).report_inbox(inbox_origin, event.data)
        except Exception:
            self.logger.warn("Could not process incoming event: {0}".format(traceback.format_exc()), event=event)


class XMLEventJoin(EventJoin):

    input = XMLEvent
    output = XMLEvent
    matched_event_class = MatchedXMLEvent


class JSONEventJoin(EventJoin):

    input = JSONEvent
    output = JSONEvent
    matched_event_class = MatchedJSONEvent
