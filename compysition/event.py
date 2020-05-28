#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  default.py
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
#
import json
import traceback
import re
import xmltodict
import urllib

from uuid import uuid4 as uuid
from lxml import etree
from copy import deepcopy
from datetime import datetime
from collections import OrderedDict, defaultdict

from .errors import (ResourceNotModified, MalformedEventData, InvalidEventDataModification, UnauthorizedEvent,
    ForbiddenEvent, ResourceNotFound, EventCommandNotAllowed, ActorTimeout, ResourceConflict, ResourceGone,
    UnprocessableEventData, EventRateExceeded, CompysitionException, ServiceUnavailable)
from .util import ignore
from .util.event import (_InternalJSONXMLConverter, _decimal_default, _NullLookupValue, 
    _UnescapedDictXMLGenerator, _InternalXWWWFORMXMLConverter, _InternalXWWWFORMJSONConverter,
    _XWWWFormList)

"""
Compysition event is created and passed by reference among actors
"""

NoneType = type(None)
DEFAULT_EVENT_SERVICE = "default"
DEFAULT = object()

setattr(xmltodict, "XMLGenerator", _UnescapedDictXMLGenerator)
_XML_TYPES = [etree._Element, etree._ElementTree, etree._XSLTResultTree]
_JSON_TYPES = [dict, list, OrderedDict]
_XWWWFORM_TYPES = [_XWWWFormList]

class DataFormatInterface(object):
    """
    Interface used as an identifier for data format classes. Used during event type conversion
    To create a new datatype, simply implement this interface on the newly created class
    """
    pass

class Event(object):

    """
    Anatomy of an event:
        - event_id: The unique and functionally immutable ID for this new event
        - meta_id:  The ID associated with other unique event data flows. This ID is used in logging
        - service:  (default: default) Used for compatability with the ZeroMQ MajorDomo configuration. Scope this to specific types of interprocess routing
        - data:     <The data passed and worked on from event to event. Mutable and variable>
        - kwargs:   All other kwargs passed upon Event instantiation will be added to the event dictionary

    """

    _content_type = "text/plain"

    def __init__(self, meta_id=None, service=None, data=None, *args, **kwargs):
        self.event_id = uuid().get_hex()
        self.meta_id = meta_id if meta_id else self.event_id
        self.service = service or DEFAULT_EVENT_SERVICE
        self.data = data
        self.error = None
        self.created = datetime.now()
        self.__dict__.update(kwargs)

    def set(self, key, value):
        with ignore(AttributeError, TypeError, ValueError):
            setattr(self, key, value)
            return True
        return False

    def get(self, key, default=DEFAULT):
        val = getattr(self, key, default)
        if val is DEFAULT:
            raise AttributeError("Event property '{property}' does not exist".format(property=key))
        return val

    @property
    def data(self):
        return self._data

    @data.setter
    def data(self, data):
        self._data = self._convert_data(data=data)

    def _convert_data(self, data):
        try:
            return self.conversion_methods[data.__class__](data)
        except KeyError as e:
            raise InvalidEventDataModification("Data of type '{_type}' was not valid for event type {cls}: {err}".format(_type=type(data),
                                                                                          cls=self.__class__, err=traceback.format_exc()))
        except ValueError as err:
            raise InvalidEventDataModification("Malformed data: {err}".format(err=err))
        except Exception as err:
            raise InvalidEventDataModification("Unknown error occurred on modification: {err}".format(err=err))

    @property
    def event_id(self):
        return self._event_id

    @event_id.setter
    def event_id(self, event_id):
        if self.get("_event_id", None):
            raise InvalidEventDataModification("Cannot alter event_id once it has been set. A new event must be created")
        self._event_id = event_id

    def _list_get(self, obj, key, default):
        with ignore(ValueError, IndexError, TypeError, KeyError, AttributeError):
            return obj[int(key)]
        return default

    def _getattr(self, obj, key, default):
        with ignore(TypeError):
            return getattr(obj, key, default)
        return default

    def _obj_get(self, obj, key, default):
        with ignore(TypeError, AttributeError):
            return obj.get(key, default)
        return default

    def lookup(self, path):
        """
        Implements the retrieval of a single list index through an integer path entry
        """
        if isinstance(path, str):
            path = [path]

        value = reduce(lambda obj, key: self._obj_get(obj, key, self._getattr(obj, key, self._list_get(obj, key, _NullLookupValue()))), [self] + path)
        if isinstance(value, _NullLookupValue):
            return None
        return value

    def get_properties(self):
        """
        Gets a dictionary of all event properties except for event.data
        Useful when event data is too large to copy in a performant manner
        """
        return {k: v for k, v in self.__dict__.iteritems() if k != "data" and k != "_data"}

    def __getstate__(self):
        return dict(self.__dict__)

    def __setstate__(self, state):
        self.__dict__ = state
        self.data = state['_data']
        self.error = state.get('_error', None)

    def __str__(self):
        return str(self.__getstate__())

    @property
    def error(self):
        return self._error

    @error.setter
    def error(self, exception):
        self._set_error(exception)

    def _set_error(self, exception):
        self._error = exception

    conversion_methods = defaultdict(lambda: lambda data: data)

    def format_error(self):
        if self.error:
            if hasattr(self.error, 'override') and self.error.override:
                return self.error.override
            messages = self.error.message
            if not isinstance(messages, list):
                messages = [messages]
            errors = map(lambda _error:
                        dict(message=str(getattr(_error, "message", _error)), **self.error.__dict__),
                        messages)
            return errors
        return None

    def error_string(self):
        return None if self.error is None else str(self.format_error())

    def data_string(self):
        return str(self.data)

    def convert(self, convert_to):
        if issubclass(convert_to, self.__class__):
            # Widening conversion
            new_class = convert_to
        else:
            if not issubclass(self.__class__, convert_to):
                # A complex widening conversion
                bases = tuple([convert_to] + filter(lambda cls: not issubclass(cls, DataFormatInterface) and not issubclass(convert_to, cls), list(self.__class__.__bases__) + [self.__class__]))
                if len(bases) == 1:
                    new_class = bases[0]
                else:
                    new_class = filter(lambda cls: cls.__bases__ == bases, built_classes)[0]
            else:
                # This is an attempted narrowing conversion
                raise InvalidEventConversion("Narrowing event conversion attempted, this is not allowed <Attempted {old} -> {new}>".format(
                        old=self.__class__, new=convert_to))

        new_class = new_class.__new__(new_class)
        new_class.__dict__.update(self.__dict__)
        new_class.data = self.data
        return new_class

    def clone(self):
        return deepcopy(self)


class HttpEvent(Event):

    content_type = "text/plain"

    def __init__(self, headers=None, status=(200, "OK"), environment={}, pagination=None, *args, **kwargs):
        self.headers = headers or {}
        self.method = environment.get('REQUEST_METHOD', None)
        self.status = status
        self.environment = environment
        self._pagination = pagination
        super(HttpEvent, self).__init__(*args, **kwargs)

    @property
    def status(self):
        return self._status

    @status.setter
    def status(self, status):
        if isinstance(status, tuple):
            self._status = status
        elif isinstance(status, str):
            status = re.split(' |-', status, 1)
            if len(status) == 2:
                self._status = (int(status[0]), status[1])

    def _set_error(self, exception):
        if isinstance(exception, Exception):
            error_state = http_code_map[exception.__class__]
            self.status = error_state.get("status")
            self.headers.update(error_state.get("headers", {}))

        super(HttpEvent, self)._set_error(exception)

    @property
    def pagination(self):
        return self._pagination

    @pagination.setter
    def pagination(self, pagination_dict):
        if 'limit' in pagination_dict and 'offset' in pagination_dict:
            self._pagination = pagination_dict
        else:
            raise ValueError('Must have limit and offset keys set in pagination_dict')

class _XMLFormatInterface(DataFormatInterface):

    content_type = "application/xml"
    _default_tab_string = "<root/>"

    conversion_methods = {str: lambda data: _XMLFormatInterface._from_string(data)}
    conversion_methods.update(dict.fromkeys(_XWWWFORM_TYPES, lambda data: _InternalXWWWFORMXMLConverter.to_xml(data)))
    conversion_methods.update(dict.fromkeys(_XML_TYPES, lambda data: data))
    conversion_methods.update(dict.fromkeys(_JSON_TYPES, lambda data: _InternalJSONXMLConverter.to_xml(data)))
    conversion_methods.update({None.__class__: lambda data: _XMLFormatInterface._from_string(data)})

    @staticmethod
    def _from_string(data):
        ####### Desired
        #if data is None or len(data) == 0:
        ####### Current
        if data is None:
        #######
            return etree.fromstring(_XMLFormatInterface._default_tab_string)
        return etree.fromstring(data)

    def __getstate__(self):
        state = super(_XMLFormatInterface, self).__getstate__()
        state['_data'] = etree.tostring(self.data)
        return state

    def data_string(self):
        return etree.tostring(self.data)

    def format_error(self):
        errors = super(_XMLFormatInterface, self).format_error()
        if self.error and self.error.override:
            try:
                return etree.fromstring(errors)
            except (ValueError, etree.XMLSyntaxError):
                return errors
        elif errors:
            result = etree.Element("errors")
            for error in errors:
                error_element = etree.Element("error")
                message_element = etree.Element("message")
                code_element = etree.Element("code")
                error_element.append(message_element)
                message_element.text = error['message']
                if getattr(error, 'code', None) or ('code' in error and error['code']):
                    code_element.text = error['code']
                    error_element.append(code_element)
                result.append(error_element)
        return result

    def error_string(self):
        error = self.format_error()
        if error is not None:
            with ignore(TypeError):
                return etree.tostring(error)
        return error

class _XMLXWWWFormFormatInterface(_XMLFormatInterface):
    '''
       Interface with the premise of HTTP requests comming in as application/x-www-form-urlencoded but desired treatment is XML
    '''

    content_type = "application/x-www-form-urlencoded"

    conversion_methods = {str: lambda data: _XMLXWWWFormFormatInterface._from_string(data)}
    conversion_methods.update(dict.fromkeys(_XWWWFORM_TYPES, lambda data: _InternalXWWWFORMXMLConverter.to_xml(data)))
    conversion_methods.update(dict.fromkeys(_XML_TYPES, lambda data: data))
    conversion_methods.update(dict.fromkeys(_JSON_TYPES, lambda data: _InternalJSONXMLConverter.to_xml(data)))
    conversion_methods.update({None.__class__: lambda data: _XMLXWWWFormFormatInterface._from_string(data)})
    
    @staticmethod
    def _from_string(data):
        if data is not None and len(data) > 0:
            for variable in data.split("&"):
                key, value = variable.split("=")
                key, value = urllib.unquote(key), urllib.unquote(value)
                if key == "XML":
                    return etree.fromstring(value)
        return etree.fromstring(_XMLFormatInterface._default_tab_string)

    def __getstate__(self):
        state = super(_XMLXWWWFormFormatInterface, self).__getstate__()
        state['_data'] = "XML={}".format(urllib.quote(etree.tostring(self.data), ''))
        return state

    def data_string(self):
        return "XML={}".format(urllib.quote(etree.tostring(self.data), ''))

    def error_string(self):
        error = self.format_error()
        if error is not None:
            with ignore(TypeError):
                return "XML={}".format(urllib.quote(etree.tostring(error), ''))
        return error

class _XWWWFormFormatInterface(DataFormatInterface):

    content_type = "application/x-www-form-urlencoded"

    conversion_methods = {str: lambda data: _XWWWFormFormatInterface._from_string(data)}
    conversion_methods.update(dict.fromkeys(_XWWWFORM_TYPES, lambda data: data))
    conversion_methods.update(dict.fromkeys(_XML_TYPES, lambda data: _InternalXWWWFORMXMLConverter.to_xwwwform(data)))
    conversion_methods.update(dict.fromkeys(_JSON_TYPES, lambda data: _InternalXWWWFORMJSONConverter.to_xwwwform(data)))
    conversion_methods.update({None.__class__: lambda data: _XWWWFormFormatInterface._from_string(data)})

    @staticmethod
    def _get_values_from_string(data):
        variables = data.split("&")
        for variable in variables:
            key, value = variable.split("=")
            yield urllib.unquote(key), urllib.unquote(value)

    @staticmethod
    def _get_objs_from_string(data):
        cur = {}
        for key, value in _XWWWFormFormatInterface._get_values_from_string(data):
            cur_key, cur_value = key, tuple()
            with ignore(StopIteration):
                cur_key, cur_value = next(cur.iteritems())
            if cur_key == key:
                cur[key] = cur_value + (value,)
            else:
                yield cur_key, cur_value
                cur = {key: (value,)}
        with ignore(StopIteration):
            yield next(cur.iteritems())

    @staticmethod
    def _from_string(data):
        if data is not None and len(data) > 0:
            return _XWWWFormList([{key: value} for key, value in _XWWWFormFormatInterface._get_objs_from_string(data)])
        return _XWWWFormList()

    @staticmethod
    def _get_objs_from_xwwwform(data):
        for obj in data:
            for key, values in obj.iteritems():
                for value in values:
                    yield key, value

    @staticmethod
    def _xwwwform_to_str(data):
        return "&".join(["{}={}".format(urllib.quote(str(key), ''), urllib.quote(str(value), '')) for key, value in _XWWWFormFormatInterface._get_objs_from_xwwwform(data)])

    def __getstate__(self):
        state = super(_XWWWFormFormatInterface, self).__getstate__()
        state['_data'] = _XWWWFormFormatInterface._xwwwform_to_str(self.data)
        return state

    def data_string(self):
        return _XWWWFormFormatInterface._xwwwform_to_str(self.data)

    def _error_messages(self, error):
        for error_obj in error:
            with ignore(KeyError):
                yield error_obj["message"]

    def error_string(self):
        error = self.format_error()
        if error is not None:
            with ignore(TypeError):
                return "&".join("error={}".format(urllib.quote(str(msg), '')) for msg in self._error_messages(error))
        return error

class _JSONFormatInterface(DataFormatInterface):

    content_type = "application/json"

    conversion_methods = {str: lambda data: _JSONFormatInterface._from_string(data)}
    conversion_methods.update(dict.fromkeys(_XWWWFORM_TYPES, lambda data: _InternalXWWWFORMJSONConverter.to_json(data)))
    conversion_methods.update(dict.fromkeys(_JSON_TYPES, lambda data: json.loads(json.dumps(data, default=_decimal_default))))
    conversion_methods.update(dict.fromkeys(_XML_TYPES, lambda data: _InternalJSONXMLConverter.to_json(data)))
    conversion_methods.update({None.__class__: lambda data: _JSONFormatInterface._from_string(data)})

    @staticmethod
    def _from_string(data):
        ####### Desired
        #return {} if data is None or len(data) == 0 else json.loads(data)
        ####### Current
        return {} if data is None else json.loads(data)
        #######

    def __getstate__(self):
        state = super(_JSONFormatInterface, self).__getstate__()
        state['_data'] = json.dumps(self.data)
        return state

    def data_string(self):
        return json.dumps(self.data, default=_decimal_default)

    def error_string(self):
        error = self.format_error()
        if error is not None:
            with ignore(TypeError):
                return json.dumps(error)
        return error

class _JSONXWWWFormFormatInterface(_JSONFormatInterface):

    content_type = "application/x-www-form-urlencoded"

    conversion_methods = {str: lambda data: _JSONXWWWFormFormatInterface._from_string(data)}
    conversion_methods.update(dict.fromkeys(_XWWWFORM_TYPES, lambda data: _InternalXWWWFORMJSONConverter.to_json(data)))
    conversion_methods.update(dict.fromkeys(_JSON_TYPES, lambda data: json.loads(json.dumps(data, default=_decimal_default))))
    conversion_methods.update(dict.fromkeys(_XML_TYPES, lambda data: _InternalJSONXMLConverter.to_json(data)))
    conversion_methods.update({None.__class__: lambda data: _JSONXWWWFormFormatInterface._from_string(data)})
    
    @staticmethod
    def _from_string(data):
        if data is not None and len(data) > 0:
            for variable in data.split("&"):
                key, value = variable.split("=")
                key, value = urllib.unquote(key), urllib.unquote(value)
                if key == "JSON":
                    return json.loads(value)
        return {}

    def __getstate__(self):
        state = super(_JSONXWWWFormFormatInterface, self).__getstate__()
        state['_data'] = "JSON={}".format(urllib.quote(json.dumps(self.data), ''))
        return state

    def data_string(self):
        return "JSON={}".format(urllib.quote(json.dumps(self.data, default=_decimal_default), ''))

    def error_string(self):
        error = self.format_error()
        print "error", error
        if error is not None:
            with ignore(TypeError):
                return "JSON={}".format(urllib.quote(json.dumps(error), ''))
        return error

class XMLEvent(_XMLFormatInterface, Event): pass
class JSONEvent(_JSONFormatInterface, Event): pass

class JSONHttpEvent(JSONEvent, HttpEvent): pass
class XMLHttpEvent(XMLEvent, HttpEvent): pass

class __XWWWFORMEvent(_XWWWFormFormatInterface, Event): pass #only internally used to ensure event structure matchs that of other event types
class __XWWWFORM_XMLEvent(_XMLXWWWFormFormatInterface, Event): pass #only internally used to distinguish inheritance between XWWWFORM_XML_HTTPEvent and XMLHttpEvent
class __XWWWFORM_JSONEvent(_JSONXWWWFormFormatInterface, Event): pass #only internally used to distinguish inheritance between __XWWWFORM_JSON_HTTPEvent and JSONHttpEvent

class _XWWWFORMHttpEvent(__XWWWFORMEvent, HttpEvent): pass #Intended for use by HttpServer to interpret x-www-form-urlencoded
class _XMLXWWWFORMHttpEvent(__XWWWFORM_XMLEvent, HttpEvent): pass #Intended for use by HttpServer to interpret x-www-form-urlencoded
class _JSONXWWWFORMHttpEvent(__XWWWFORM_JSONEvent, HttpEvent): pass #Intended for use by HttpServer to interpret x-www-form-urlencoded

class LogEvent(Event):
    """
    This is a lightweight event designed to mimic some of the event properties of a regular event
    """

    def __init__(self, level, origin_actor, message, id=None):
        self.id = id
        self.event_id = uuid().get_hex()
        self.meta_id = id or self.event_id
        self.level = level
        self.time = datetime.now().strftime('%Y-%m-%d %H:%M:%S,%f')[:-3]
        self.origin_actor = origin_actor
        self.message = message
        self.data = {"id":              self.id,
                    "level":            self.level,
                    "time":             self.time,
                    "origin_actor":     self.origin_actor,
                    "message":          self.message}

built_classes = [Event, XMLEvent, JSONEvent, HttpEvent, JSONHttpEvent, XMLHttpEvent, LogEvent, _XWWWFORMHttpEvent, _XMLXWWWFORMHttpEvent, _JSONXWWWFORMHttpEvent]
__all__ = map(lambda cls: cls.__name__, built_classes)

http_code_map = defaultdict(lambda: {"status": ((500, "Internal Server Error"))},
                            {
                                ResourceNotModified:    {"status": (304, "Not Modified")},
                                MalformedEventData:     {"status": (400, "Bad Request")},
                                InvalidEventDataModification: {"status": (400, "Bad Request")},
                                UnauthorizedEvent:      {"status": (401, "Unauthorized"),
                                                         "headers": {'WWW-Authenticate': 'Basic realm="Compysition Server"'}},
                                ForbiddenEvent:         {"status": (403, "Forbidden")},
                                ResourceNotFound:       {"status": (404, "Not Found")},
                                EventCommandNotAllowed: {"status": (405, "Method Not Allowed")},
                                ActorTimeout:           {"status": (408, "Request Timeout")},
                                ResourceConflict:       {"status": (409, "Conflict")},
                                ResourceGone:           {"status": (410, "Gone")},
                                UnprocessableEventData: {"status": (422, "Unprocessable Entity")},
                                EventRateExceeded:      {"status": (429, "Too Many Requests")},
                                CompysitionException:   {"status": (500, "Internal Server Error")},
                                ServiceUnavailable:     {"status": (503, "Service Unavailable")},
                                NoneType:               {"status": (200, "OK")}         # Clear an error
                            })

__all__.append(http_code_map)