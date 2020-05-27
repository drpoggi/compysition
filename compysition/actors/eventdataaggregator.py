#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
#  tagaggregator.py
#
#  Copyright 2014 Adam Fiebig <fiebig.adam@gmail.com>
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
from lxml import etree

from compysition.actor import Actor
from compysition.util import itervalues

"""
DEPRECATED

With the changes in 1.1.43-dev, WSGI no longer reflects x-www-form-urlencoding tags in generated events... which was the primary
use case for this module. There is hardly any reason for it to exist at this point
"""

class EventDataAggregator(Actor):
    '''**Simple module which aggregates all existing tags under event.data together as event.data. Default module does simple string concatenation
    e.g. event.data['tagone'] and event.data['tagtwo'] become event.data, where data equals event.data['tagone'] + event.data['tagone']**
    '''

    def __init__(self, name, *args, **kwargs):
        super(EventDataAggregator, self).__init__(name, *args, **kwargs)
        self.key = kwargs.get("key", name)

    def consume(self, event, *args, **kwargs):
        if isinstance(event.data, dict):
            try:
                event.data = self._do_aggregation(event.data)
            except Exception as err:
                self.logger.error("Could not aggregate tags under event data. Reason {0}".format(err), event=event)

        self.send_event(event)

    def _do_aggregation(self, data_dict):
        return_value = ""
        for key in data_dict:
            if data_dict[key] is not None:
                return_value += data_dict[key]

        return return_value

class EventDataXMLAggregator(EventDataAggregator):
    '''**Simple module which aggregates all existing tags under event.data together as event.data, under a single root XML element**
    '''

    def _do_aggregation(self, data_dict):
        return_value = None
        if len(data_dict) > 1:
            root_node = etree.Element(self.key)
            for key in data_dict:
                try:
                    xml = etree.XML(data_dict[key])
                    root_node.append(xml)
                except Exception as err:
                    self.logger.error("Submitted tag value was not valid XML. Skipping: {0}".format(err))

            return_value = etree.tostring(root_node)
        elif len(data_dict) == 1:
            return_value = next(itervalues(data_dict))

        return return_value
