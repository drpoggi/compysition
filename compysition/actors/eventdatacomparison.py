#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
#  eventdatacomparison.py
#
#  Copyright 2020 CU*Answers Integrations <integrations@cuanswers.com>
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

from compysition.actor import Actor
import operator

class EventDataCompare(Actor):
    '''**Comparison operators against data in the events**
        Initially this is going to test if values are equal to each other.
        Eventually we can add the remaining comparison operators.

    Parameters:

        name (str):
            | Name of the instance
        left (str):
            | Left comparison value.
        right (str):
            | Right comparison value

    '''
    def __init__(self, name, left, right, *args, **kwargs):
        super(EventDataCompare, self).__init__(name, *args, **kwargs)
        self.left = left
        self.right = right

    def consume(self, event, *args, **kwargs):
        #event.data.compare_result = operator.eq(event.data.get(self.left), event.data.get(self.right))
        self.logger.info("Preparing to compare: {0} with: {1}".format(self.left, self.right), event=event)
        try:
            event.data["comparison_result"] = operator.eq(event.data.get(self.left), event.data.get(self.right))
        except Exception as err:
            self.logger.error("Could not compare results. Reason {0}".format(err), event=event)
        self.send_event(event)