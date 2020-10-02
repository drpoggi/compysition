#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
#  header.py
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

import re
import functools

from lxml import etree

from .util.xpath import XPathLookup
from compysition.actor import Actor
from compysition.event import XMLEvent, JSONEvent
from compysition.errors import MalformedEventData, CompysitionException

class _FormatErrorInsertMixin:
    def get_modify_value(self, event):
        value = event.format_error()
        if not value:
            value = event.data
        return value

class EventAttributeModifier(Actor):

    '''**Adds or updates static information to an event**

    Parameters:

        - name  (str):          The instance name.
        - key   (str):          (Default: "data") The key to set or update on the incoming event. Can be a key-chain
                                    to access recursive dictionary elements using 'separator'
        - value (Anything):     (Default: {}) The value to assign to the key
        - separator (str)       (Default: "/") Delimiter for recursive key lookups
    '''

    def __init__(self, name, key='data', value={}, log_change=False, separator="/", *args, **kwargs):
        super(EventAttributeModifier, self).__init__(name, *args, **kwargs)
        self.value = value
        self.separator = separator
        if key is None:
            self.key = name
        else:
            self.key = key

        self.log_change = log_change

    def consume(self, event, *args, **kwargs):
        modify_value = self.get_modify_value(event)

        if self.log_change:
            self.logger.info("Changed event.{key} to {value}".format(key=self.key, value=modify_value), event=event)

        try:
            event = self.get_key_chain_value(event, modify_value)
            self.send_event(event)
        except Exception as err:
            raise MalformedEventData(err)

    def get_key_chain_value(self, event, value):
        #TODO: Redo this to not modify arrays
        keys = self.key.split(self.separator)
        event_key = keys.pop(0)
        if len(keys) == 0:
            event.set(event_key, value)
        else:
            current_step = event.get(event_key, None)
            if not current_step:
                current_step = {}
                event.set(event_key, current_step)

            try:
                while True:
                    try:
                        item = keys.pop(0)
                        if len(keys) > 0:
                            next_step = current_step[item]
                            current_step = next_step
                        else:
                            current_step[item] = value
                    except KeyError:
                        next_step = {} if len(keys) > 0 else value
                        current_step[item] = next_step
                        current_step = next_step
                    except IndexError:
                        break
            except Exception as err:
                self.logger.error("Unable to follow key chain. Ran into non-dict value of '{value}'".format(value=current_step), event=event)
                raise

        return event

    def get_modify_value(self, event):
        return self.value


class EventAttributeLookupModifier(EventAttributeModifier):

    def get_modify_value(self, event):
        return event.lookup(self.value)


class EventAttributeDelete(Actor):
    """ Deletes information from an event**

                Parameters:

                    - name         (str):   The instance name.
                    - key_paths   (list):   A list of attributes to be deleted"""

    def __init__(self, name, key_paths=None, log_failed_delete=True, *args, **kwargs):
        super(EventAttributeDelete, self).__init__(name, *args, **kwargs)
        self.key_paths = key_paths
        self.log_failed_delete = log_failed_delete

        if self.key_paths is None:
            raise ValueError('key_paths cannot be None')

        if not isinstance(self.key_paths, list):
            self.key_paths = [self.key_paths]

        self.key_paths = [[path] if not isinstance(path, list) else path for path in self.key_paths]

    def consume(self, event, *args, **kwargs):
        # create copy so we're not iterating over mutable defaults, whoops...
        key_paths = [path[:] for path in self.key_paths]

        try:
            for path in key_paths:
                self.delete(event, path)
                self.logger.info('Deleted event attribute: {attr}'.format(attr=path), event=event)
        except Exception as error:
            if self.log_failed_delete:
                self.logger.error('Failed to delete attribute <{attr}> from event: {error}'.format(
                    attr=self.key_paths, error=error), event=event)

        self.send_event(event)

    def delete(self, event, path):
        try:
            delattr(event, path[0])
        except AttributeError:
            self.logger.error('Failed to delete attribute {attr} from event'.format(attr=path[0]), event=event)



class JSONEventAttributeDelete(EventAttributeDelete):
    """
        Deletes information from an event**

                Parameters:

                    - name         (str):   The instance name.
                    - key_paths   (list):   A list of lists, with the inner list defining the path to the keys to deleted
                                            key_paths=[['event_attr], ['data', 'fruits', 'apple']

        Example:
            Given event JSONEvent(data={'fruits': {'apple': 1, 'banana': 3}, 'count': 2}) and a value for key_paths
            of [['data', 'fruits', 'apple']], the outputed event.data will be {'count': 2, 'fruits': {'banana': 3}"""

    input = JSONEvent
    output = JSONEvent

    def delete(self, event, path):
        if len(path) == 1:
            try:
                delattr(event, path[0])
            except AttributeError:
                event.pop(path[0])
        else:
            self.delete(event.get(path.pop(0)), path)

class HTTPStatusModifier(EventAttributeModifier):

    def __init__(self, name, value=(200, "OK"), *args, **kwargs):
        super(HTTPStatusModifier, self).__init__(name, key="status", value=value, *args, **kwargs)


class XpathEventAttributeModifier(EventAttributeModifier):

    input = XMLEvent
    output = XMLEvent

    def get_modify_value(self, event):
        lookup = XPathLookup(event.data)
        xpath_lookup = lookup.lookup(self.value)

        if len(xpath_lookup) <= 0:
            value = None
        elif len(xpath_lookup) == 1:
            value = XpathEventAttributeModifier._parse_result_value(xpath_lookup[0])
        else:
            value = []
            for result in xpath_lookup:
                value.append(XpathEventAttributeModifier._parse_result_value(result))

        return value

    @staticmethod
    def _parse_result_value(result):
        value = None
        if isinstance(result, etree._ElementStringResult):
            value = result
        elif isinstance(result, (etree._Element, etree._ElementTree)):
            if len(result.getchildren()) > 0:

                value = etree.tostring(result)
            else:
                value = result.text

        return value

class HTTPXpathEventAttributeModifier(XpathEventAttributeModifier, HTTPStatusModifier):
    pass

class JSONEventAttributeModifier(EventAttributeModifier):

    input = JSONEvent
    output = JSONEvent

    def __init__(self, name, separator="/", *args, **kwargs):
        self.separator = separator
        super(JSONEventAttributeModifier, self).__init__(name, *args, **kwargs)

    def get_modify_value(self, event):
        data = event.data
        if isinstance(data, list):
            for datum in data:
                value = functools.reduce(lambda acc, key: acc.get(key, {}), [datum] + self.value.split(self.separator))
                if value is not None:
                    break
        else:
            value = functools.reduce(lambda acc, key: acc.get(key, {}), [data] + self.value.split(self.separator))

        if isinstance(value, dict) and len(value) == 0:
            value = None

        return value

class HTTPJSONAttributeModifier(JSONEventAttributeModifier, HTTPStatusModifier):
    pass


class XMLEventAttributeModifier(EventAttributeModifier):
    input = XMLEvent
    
    def get_key_chain_value(self, event, value):
        keys = self.key.split(self.separator)
        event_key = keys.pop(0)
        if len(keys) == 0:
            event.set(event_key, value)
        else:
            root_element = event.get(event_key, None)
            current_element = root_element

            try:
                item = keys.pop(0)
                if not item == current_element.tag:
                    raise
                while True:
                    if len(keys) > 0:
                        item = keys.pop(0)
                        next_step = current_element.find(item)
                        if not etree.iselement(next_step):
                            next_step = etree.Element(item)
                            current_element.append(next_step)
                        current_element = next_step
                    else:
                        current_element.text = str(value)
                        break
            except Exception as err:
                self.logger.error("Unable to follow key chain. Ran into non-xml value of '{value}'".format(value=current_element), event=event)
                raise

        return event

class XMLEventAttributeLookupModifier(XMLEventAttributeModifier, EventAttributeLookupModifier):
    pass

class ErrorEventAttributeModifier(Actor):
    '''
    Description:
        Allows for custom errors.

    Uses:
        - Adjusting error (message, code) staticly
        - Adding http error response format (override)
        - Adjusting error class

    Parameters:

        - name:                                             (See Actor)
        - override (bool):                                  Specifies whether the event.data is to be used as the http response.  (True uses event.data as http response)
        - code (str):                                       Specifies the static error code. (EX: 6768)
        - message (str):                                    Specifies the static error message. (EX: "Unknown Error Occured")
        - error_class (CompysitionError class):             Specifies the error class to be used (forceful).  Otherwise uses same class as the input event.error.
        - default_error_class (CompysitionError class):     Specifies the default error class.  Only used when incoming event does not already have an error and error_class is not set.
    '''
    def __init__(self, name, override=False, code=None, message=None, error_class=None, default_error_class=MalformedEventData, *args, **kwargs):
        self.message = message
        self.code = code
        self.override = override
        self.error_class = error_class
        self.default_error_class = default_error_class
        super(ErrorEventAttributeModifier, self).__init__(name=name, *args, **kwargs)

    def consume(self, event, *args, **kwargs):
        override = event.data_string() if self.override else None
        message = self._get_message(event)
        code = self._get_code(event)
        clazz = event.error.__class__ if event.error and isinstance(event.error, CompysitionException) else self.default_error_class
        clazz = self.error_class if self.error_class else clazz

        event._set_error(clazz(message=message, code=code, override=override))
        self.send_event(event)

    def _get_message(self, event):
        return (self.message if self.message else event.data_string())

    def _get_code(self, event):
        return (self.code if self.code else None)

class XMLErrorEventAttributeModifier(ErrorEventAttributeModifier):
    '''
    Description:
        Allows for custom errors as they pertain to incoming XML event.data.

    Uses:
        - Adjusting error (message, code) staticly
        - Adding http error response format (override)
        - Adjusting error class

    Example XML input:
        <data>
            <response>
                <response_message>Something went wrong.</response_message>
                <response_code>6768<response_code>
                <response_id>1234<response_id>
            </response>
        </data>

    Parameters:

        - name:                                             (See Actor)
        - override (bool):                                  (See ErrorEventAttributeModifier)
        - code (str):                                       (See ErrorEventAttributeModifier)
        - code_attr (str)                                   Specifies the variable from an incoming event.data XML object to be used as the new error code.
                                                                Attribute specified by a '.' seperated attribute list.  (EX: "data.response.response_code")
                                                                If the variable is missing then a static code is used if provided.
        - message (str):                                    (See ErrorEventAttributeModifier)
        - message_attr (str):                               Specifies the variable from an incoming event.data XML object to be used as the new error message.
                                                                Attribute specified by a '.' seperated attribute list.  (EX: "data.response.response_message")
                                                                If the variable is missing then a static message is used if provided.
        - error_class (CompysitionError class):             (See ErrorEventAttributeModifier)
        - default_error_class (CompysitionError class):     (See ErrorEventAttributeModifier)
    '''
    def __init__(self, name, override=False, code=None, code_attr=None, message=None, message_attr=None, error_class=None, default_error_class=MalformedEventData, *args, **kwargs):
        self.message_attr = message_attr
        self.code_attr = code_attr
        super(XMLErrorEventAttributeModifier, self).__init__(name=name, override=override, code=code, message=message, error_class=error_class, default_error_class=default_error_class, *args, **kwargs)

    def _get_attr(self, event, attr):
        try:
            json_event = event.convert(JSONEvent)
            cur = json_event.data
            for cur_attr in attr.split("."):
                cur = cur[cur_attr]
            if cur == None or cur == "":
                return "Unknown Error Occured"
            if not cur == json_event.data:
                return cur
        except Exception:
            pass
        return None

    def _get_message(self, event):
        value = self._get_attr(event=event, attr=self.message_attr)
        return (value if value else super(XMLErrorEventAttributeModifier, self)._get_message(event))

    def _get_code(self, event):
        value = self._get_attr(event=event, attr=self.code_attr)
        return (value if value else super(XMLErrorEventAttributeModifier, self)._get_code(event))

class EventDataEventAttributeModifier(EventAttributeModifier):

    """This will allow you to modify the event data to contain something that exists directly on the event.
    IF your data is a list (like after the json db write), it's going to reinitialize it
    as a dict. This will use self.key (what you called it with) to both get it from the event
    and name the resulting data attribute."""

    def get_modify_value(self, event):
        value = getattr(event, self.key)
        event.data = {self.key:value}
        return value

class EventDataStaticAttributeModifier(EventAttributeModifier):

    """This will allow you to modify the event data to contain any static value that you send.
    IF your data is a list (like after the json db write), it's going to reinitialize it
    as a dict."""
    
    def get_modify_value(self, event):
        event.data = {self.key:self.value}
        return self.value


class EventAttributeRegexSubstitution(Actor):
    """ Allow you to replace parts of string values on event attributes"""

    def __init__(self, name, pattern="*", event_attr=None, replace_with="", *args, **kwargs):
        super(EventAttributeRegexSubstitution, self).__init__(name, *args, **kwargs)

        if event_attr is None:
            raise ValueError("event_attr must be defined")

        self.pattern = pattern
        self.event_attr = event_attr
        self.replace_with = replace_with

    def consume(self, event, *args, **kwargs):
        value = event.lookup(self.event_attr)
        value = re.sub(self.pattern, self.replace_with, value)
        event.set(self.event_attr, value)
        self.send_event(event)

class FormatErrorModifyEventAttribute(_FormatErrorInsertMixin, EventAttributeModifier):
    pass
