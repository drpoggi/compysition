#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
#  transformer.py
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

import traceback

from lxml import etree
from lxml.etree import XSLTApplyError #TODO Don't need this and generic etree import

from compysition.actor import Actor
from compysition.event import XMLEvent, JSONEvent
from compysition.errors import MalformedEventData

__all__ = [
    "XSLT",
    "JSONXSLT",
    "XMLXSLT"
]

class _XSLT(Actor):
    '''**A sample module which applies a provided XSLT to an incoming event XML data**

    Parameters:

        name (str):
            | The instance name.
        xslt (str):
            | The xslt to apply to incoming XMLEvent

    Input:
        XMLEvent

    Output:
        XMLEvent

    '''

    input = XMLEvent

    def __init__(self, name, xslt=None, *args, **kwargs):
        super(_XSLT, self).__init__(name, *args, **kwargs)

        if xslt is None and not isinstance(xslt, str):
            raise TypeError("Invalid xslt defined. {_type} is not a valid xslt. Expected 'str'".format(_type=type(xslt)))
        else:
            self.template = etree.XSLT(etree.XML(xslt))

    def consume(self, event, *args, **kwargs):
        try:
            self.logger.debug("In: {data}".format(data=event.data_string().replace('\n', '')), event=event)
            event.data = self.transform(event.data)
            self.logger.debug("Out: {data}".format(data=event.data_string().replace('\n', '')), event=event)
            self.logger.info("Successfully transformed XML", event=event)
            self.send_event(event)
        except XSLTApplyError as err:
            # This is a legacy functionality that was implemented due to the specifics of a single implementation.
            # I'm looking for a way around this, internally
            event.data.append(etree.fromstring("<transform_error>{0}</transform_error>".format(str(err))))
            self._process_error(str(err), event)
        except Exception as err:
            self._process_error(traceback.format_exc(), event)

    def _process_error(self, message, event):
        self.logger.error("Error applying transform. Error was: {0}".format(message), event=event)
        raise MalformedEventData("Malformed Request: Invalid XML")

    def transform(self, etree_element):
        return self.template(etree_element).getroot()

class XSLT(_XSLT):
    output = XMLEvent

class XMLXSLT(XSLT):
    pass

class JSONXSLT(_XSLT):
    output = JSONEvent