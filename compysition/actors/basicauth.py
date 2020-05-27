#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
#  basicauth.py
#
#  Copyright 2014 James Hulett <james.hulett@cuanswers.com>
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

import base64

from compysition.actor import Actor
from compysition.errors import UnauthorizedEvent, ForbiddenEvent
from compysition.util import try_encode, try_decode

class BasicAuth(Actor):
    '''**Sample module demonstrating http basic auth. This module should be subclassed and implemented in a specific manner**
    '''

    def __init__(self, name, *args, **kwargs):
        super(BasicAuth, self).__init__(name, *args, **kwargs)

    def _extract_credentials(self, event):
        try:
            authorization = event.environment['HTTP_AUTHORIZATION']
            tokens = authorization.strip().split(' ')
            basic_token = tokens[0]
            assert len(tokens) == 2
            assert basic_token == 'Basic'
            user, password = try_decode(base64.decodestring(try_encode(tokens[1]))).split(':')
            return user, password
        except (AttributeError, KeyError):
            raise UnauthorizedEvent("No auth headers present in submitted request")
        except (AssertionError, ValueError, Exception):
            raise UnauthorizedEvent("Invalid auth headers present in submitted request")

    def _process_authentication(self, event, user, password):
        if self._authenticate(user, password):
            self.logger.info("Authorization successful", event=event)
            self.send_event(event)
        else:
            message = "Authorization Failed for user {0}".format(user)
            self.logger.info(message, event=event)
            raise UnauthorizedEvent(message)        

    def _process_authentication_error(self, event, error):
        self.logger.warn("Authorization Failed: {0}".format(error), event=event)
        event.status = '401 Unauthorized'
        event.set('headers', event.get('headers', {}))
        event.headers.update({'WWW-Authenticate': 'Basic realm="Compysition Authentication"'})
        self.send_error(event)

    def consume(self, event, *args, **kwargs):
        try:
            user, password = self._extract_credentials(event=event)
            self._process_authentication(event=event, user=user, password=password)
        except (UnauthorizedEvent, Exception) as err:
            self._process_authentication_error(event=event, error=err)

    def _authenticate(self, username, password):
        """ The method to be implemented in a manner specific to an organization """
        #self.logger.error("Error, attempted to use an un-implemented version of the basicauth module. This is not safe, please implement the _authenticate method in this module")
        raise NotImplementedError("Non-implemented authenticate module")
