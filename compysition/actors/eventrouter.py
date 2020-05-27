#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
#  xmlfilter.py
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

import json
import re

from lxml import etree

from .util.xpath import XPathLookup
from compysition.actor import Actor
from compysition.event import HttpEvent
from compysition.errors import SetupError, EventCommandNotAllowed
from compysition.util import ignore

class EventRouter(Actor):

    """**A module that filters incoming events to specific outboxes depending the input "Filter" args**

    Parameters:

        name (str):
            | The instance name.
        routing_filters (list[EventFilter]):
            | Array of "EventFilter" objects. Defaults to [] to allow for an implementing process to set these via the "set_filter" method
            | (Default: [])
        type (Optional[str]):
            | Either "whitelist" or "blacklist" -  If an event fails to match any defined filters, a "whitelist" EventRouter
            | will purge the event entirely. A "blacklist" EventRouter will use the provided 'default_outbox' parameter to forward the event
            | (Default: whitelist)
        default_outbox_regexes (Optional[str or List[str]]):
            | Only used for a "blacklist" EventRouter. If an EventRouter is "blacklist" and fails to match any provided filters,
            | the event will be output to all connected outboxes that do not have an explicit filter condition declared, that match the
            | regex(es) provided
            | (Default: .*)

    """

    def __init__(self, name, routing_filters=[], type="whitelist", default_outbox_regexes=[".*"], *args, **kwargs):
        super(EventRouter, self).__init__(name, *args, **kwargs)
        self.blockdiag_config["shape"] = "flowchart.condition"
        self.filters = []
        self.default_outbox_regexes = default_outbox_regexes if isinstance(default_outbox_regexes, list) else [default_outbox_regexes]
        self.default_outboxes = []
        if not isinstance(routing_filters, list):
            routing_filters = [routing_filters]

        for filter in routing_filters:
            self.set_filter(filter)

        if type is "whitelist":
            self.whitelist = True
        else:
            self.whitelist = False

    def pre_hook(self):
        if len(self.filters) == 0 and (len(self.default_outboxes) == 0 and self.whitelist):
            raise SetupError("No filters were connected to this router")
        self._initialize_outboxes()

    def _initialize_outboxes(self):
        self._initialize_filter_outboxes()
        if not self.whitelist:
            self._initialize_default_outboxes()

    def _initialize_default_outboxes(self):
        """Check to see which outboxes are 'filtered' outboxes,
        as we do not want to include these in a "default" outbox list"""

        filtered_outboxes = set()
        for filter in self.filters:
            for outbox in filter.outbox_names:
                filtered_outboxes.add(outbox)

        # Determine default outboxes for a 'blacklist' routing scenario
        for default_outbox_regex in self.default_outbox_regexes:
            outbox_regex = re.compile(default_outbox_regex)
            for outbox_name in self.pool.outbound:
                if outbox_name not in filtered_outboxes:
                    if outbox_regex.search(outbox_name):
                        self.default_outboxes.append(self.pool.outbound[outbox_name])

    def _initialize_filter_outboxes(self):
        """
        This method is called in pre_hook and converts the 'outboxes' on the provided filters from a string to the actual queue object
        """
        for filter in self.filters:
            for outbox_name in filter.outbox_names:
                try:
                    filter.outboxes.append(self.pool.outbound[outbox_name])
                except Exception as err:
                    raise Exception(
                        "Queue {outbox_name} was referenced in a filter, but is not connected as a valid outbox for {name}. Connected outboxes are {queue_list}. Exception was: {exception}".format(
                            outbox_name=outbox_name, name=self.name, queue_list=self.pool.outbound,
                            exception=err))

    def consume(self, event, *args, **kwargs):
        matched = False
        for filter in self.filters:
            if filter.matches(event):
                matched = True
                if len(filter.outboxes) > 0:
                    self.send_event(event, queues=filter.outboxes)
                    self.logger.debug("EventFilter matched for outbound queues ({outbox_names}). Event successfully forwarded".format(
                            outbox_names=filter.outbox_names),
                        event=event)
                else:
                    self.logger.info("EventFilter matched, but no outbound queues were defined for filter. Event has been discarded.", event=event)

        if not matched:
            self.process_no_match(event)

    def process_no_match(self, event, *args, **kwargs):
        if not self.whitelist:
            if len(self.default_outboxes) > 0:
                self.send_event(event, queues=self.default_outboxes)
                self.logger.debug("No EventFilters matched for event. Event forwarded to default outbox(s)",
                                  event=event)
            else:
                self.logger.info(
                    "No EventFilters matched for event and no default queues are connected. Event has been discarded",
                    event=event)
        else:
            self.logger.debug("No EventFilters matched for event. Event has been discarded", event=event)

    def set_filter(self, filter):
        if isinstance(filter, EventFilter):
            self.filters.append(filter)
        else:
            raise TypeError("The provided filter is not a valid EventFilter type")


class SimpleRouter(EventRouter):

    def __init__(self, name, default_queue="default", scope="data", type="blacklist", *args, **kwargs):
        super(SimpleRouter, self).__init__(name, type=type, *args, **kwargs)
        self.default_queue = default_queue
        self.scope = scope

    def pre_hook(self):
        for queue in self.pool.outbound:
            if queue != self.default_queue:
                self.set_filter(EventFilter(value_regexes=queue, outbox_names=[queue], event_scope=(self.scope, )))

        super(SimpleRouter, self).pre_hook()


class HTTPMethodEventRouter(EventRouter):

    HTTP_METHODS = ["GET", "POST", "DELETE", "PATCH", "HEAD", "PUT", "OPTIONS"]
    input = HttpEvent
    output = HttpEvent

    def __init__(self, name, *args, **kwargs):
        super(HTTPMethodEventRouter, self).__init__(name, type="blacklist", *args, **kwargs)

    def process_no_match(self, event, *args, **kwargs):
        event.headers['Allow'] = ", ".join(self.pool.outbound)
        self.logger.warning("HttpEvent with method '{method}' received but not implemented. Recommend catching this at the front end web interface".format(
                method=event.method), event=event)
        raise EventCommandNotAllowed("Method '{method}' not allowed for this endpoint".format(method=event.method))

    def pre_hook(self):
        for queue in self.pool.outbound:
            if queue in self.HTTP_METHODS:
                self.set_filter(EventFilter(value_regexes=queue, outbox_names=[queue], event_scope=("method", )))
            else:
                self.logger.warn("Queue {queue} is not a valid HTTP method and was not added as a routing option")

        super(HTTPMethodEventRouter, self).pre_hook()


class EventFilter(object):
    '''
    **A filter class to be used as a constructor argument for the EventRouter class. This class contains information about event
    match information and the outbox result of a successful match. Uses either regex match or literal equivalents**

    Parameters:
        value_regexes (Optional[[str] or str]):
            | The value(s) that will cause this filter to match. This is evaluated as a regex
            | Default: [".*"]
        outbox_names (Optional[[str] or str]):
            | The desired outbox that a positive filter match should place the event on
            | If this is not defined, the matching event will be discarded
            | Default: [0]
        event_scope (tuple(str)):
            | The string address of the location of the string value to check against this filter in an event, provided as a tuple chain
            | The scope step can either be a dictionary key or an object property
            | e.g. event.service == ("service",)
            | e.g. event.data == ("data",)
            | e.g. event.header['http'] == ("header", "http")
            | e.g. event.header.someotherobj == ("header", "someotherobj")
        next_filter(Optional[EventFilter]):
            | This grants the ability to create complex matching scenarios. "If X = match, then check Y"
            | A positive match on this filter (X), will trigger another check on filter (Y), and then use the filter configured on filter Y
            | in the event of a positive match
            | (Default: None)

    '''

    def __init__(self, value_regexes=".*",
                 outbox_names=[],
                 event_scope=("data",),
                 next_filter=None, *args, **kwargs):

        self._validate_scope_definition(event_scope)
        if not isinstance(value_regexes, list):
            value_regexes = [value_regexes]

        if not isinstance(outbox_names, list):
            outbox_names = [outbox_names]

        self.value_regexes = self.parse_value_regexes(value_regexes)
        self.outbox_names = outbox_names
        self.outboxes = []  # To be filled and defined later when the EventRouter initializes outboxes
        self.next_filter = self.set_next_filter(next_filter)

    def parse_value_regexes(self, value_regexes):
        return [re.compile(value_regex) for value_regex in value_regexes]

    def _validate_scope_definition(self, event_scope):
        if isinstance(event_scope, tuple):
            self.event_scope = event_scope
        elif isinstance(event_scope, str):
            self.event_scope = (event_scope,)
        else:
            raise TypeError("The defined event_scope must be either type str or tuple(str)")

    def set_next_filter(self, filter):
        if filter is not None:
            if isinstance(filter, EventFilter):
                self.next_filter = filter
            else:
                raise TypeError("The provided filter is not a valid EventFilter type")
        else:
            self.next_filter = None

    def matches(self, event):
        values = self._get_value(event, self.event_scope)
        try:
            for value in values:
                if value is not None:
                    for value_regex in self.value_regexes:
                        if value_regex.search(str(value)):
                            if self.next_filter:
                                return self.next_filter.matches(event)
                            else:
                                return True
        except StopIteration:
            pass
        except Exception as err:
            raise Exception(
                "Error in attempting to apply regex patterns {0} to {1}: {2}".format(self.value_regexes, values, err))

        return False

    def _get_value(self, event, event_scope, *args, **kwargs):
        """
        This method iterates through the self.event_scope tuple in a series of getattr or get calls,
        depending on if the event in the scope step is a dict or an object. More supported types may be added in the future
        If the chain fails at any point, a None is returned
        """
        try:
            current_step = event
            for scope_step in event_scope:
                if isinstance(current_step, dict):
                    current_step = current_step.get(scope_step, None)
                elif isinstance(current_step, (tuple, list)):
                    current_step = current_step[scope_step]
                elif isinstance(current_step, object):
                    # This is confusing, as everything is an object, so this is always True. Leaving in for now.
                    current_step = getattr(current_step, scope_step, None)
        except Exception as err:
            current_step = None

        yield current_step


class EventXMLFilter(EventFilter):
    '''
    **A filter class for the EventRouter module that will additionally use xpath lookup values to apply a regex comparison**
    '''

    def __init__(self, xpath=None, xslt=None, *args, **kwargs):

        super(EventXMLFilter, self).__init__(*args, **kwargs)
        self.xpath = xpath

        if xslt:
            xslt = etree.XSLT(etree.XML(xslt))

        self.xslt = xslt

    def _get_value(self, event, event_scope, xpath=None, *args, **kwargs):
        value = next(super(EventXMLFilter, self)._get_value(event, event_scope))
        xpath = xpath or self.xpath
        try:
            xml = value

            if self.xslt:
                xml = self.xslt(xml)

            lookup = XPathLookup(xml)
            xpath_lookup = lookup.lookup(xpath)

            if len(xpath_lookup) == 0:
                yield None
            else:
                for result in xpath_lookup:
                    yield self._parse_xpath_result(result)
        except Exception as err:
            yield None

    def _parse_xpath_result(self, lookup_result):
        try:
            if isinstance(lookup_result, (etree._ElementStringResult, str)):
                value = lookup_result
            else:
                value = lookup_result.text

            # We want to be able to mimic the behavior of "If this tag exists at all, even if it's blank, forward it"
            if value is None:
                value = ""
        except Exception as err:
            value = None

        return value


class EventXMLXpathsFilter(EventXMLFilter):

    """
    **A filter that uses the results from one xpath lookup to compare to the values from a second xpath lookup. A dynamic
    definition of 'value_regexes' based on the lookup of 'value_xpath'

    Parameters:
        value_xpath (str):
            | An xpath that will look up the value(s) of the regexes to be compared to the 'xpath' lookup result
            | Follows standard xpath formatting
    """

    def __init__(self, regex_xpath=None, *args, **kwargs):
        super(EventXMLXpathsFilter, self).__init__(value_regexes=[], *args, **kwargs)
        self.regex_xpath = regex_xpath

    def matches(self, event):
        new_regexes = []
        regex_values = self._get_value(event, self.event_scope, xpath=self.regex_xpath)
        with ignore(StopIteration):
            for regex in regex_values:
                if regex is not None:
                    new_regexes.append(regex)

        self.value_regexes = self.parse_value_regexes(new_regexes)
        return super(EventXMLXpathsFilter, self).matches(event)


class EventJSONFilter(EventFilter):
    # Why is this necessary? Shouldn't this just be the default chain lookup?
    #TODO Figure out if this is necessary
    '''
    **A filter class for the EventRouter module that will additionally use json lookup values to apply a regex comparison**
    '''

    def __init__(self, json_scope=None, *args, **kwargs):
        super(EventJSONFilter, self).__init__(*args, **kwargs)
        self.json_scope = json_scope

    def _get_value(self, event, event_scope):
        values = next(super(EventJSONFilter, self)._get_value(event, self.event_scope))
        try:

            if isinstance(values, str):
                values = json.loads(values)

            if isinstance(values, list):
                for value in values:
                    json_value = next(super(EventJSONFilter, self)._get_value(value, self.json_scope))
                    yield json_value
            else:
                json_value = next(super(EventJSONFilter, self)._get_value(values, self.json_scope))
                yield json_value
        except Exception as err:
            yield None



