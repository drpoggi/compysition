#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
#  cookietest.py
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

import Cookie
import datetime

from compysition.actor import Actor
from compysition.util import get_uuid, itervalues

class SetCookie(Actor):

    def __init__(self, name, cookie_key="session", cookie_value="session_value", value_mode="static", expiry=6000, path="/", *args, **kwargs):
        super(SetCookie, self).__init__(name, *args, **kwargs)
        self.cookie_key = cookie_key
        self.expiry = expiry
        self.path = path
        self.value_mode = value_mode
        self.cookie_value = cookie_value

    @property
    def cookie_value(self):
        if self.value_mode != "static":
            return get_uuid()
        else:
            return self._cookie_value

    @cookie_value.setter
    def cookie_value(self, cookie_value):
        self._cookie_value = cookie_value

    def consume(self, event, *args, **kwargs):
        try:
            session_cookie = Cookie.SimpleCookie()
            session_cookie[self.cookie_key] = self.cookie_value
            session_cookie[self.cookie_key]["Path"] = self.path
            session_cookie[self.cookie_key]['expires'] = str(datetime.datetime() + datetime.timedelta(0, self.expiry))
            event.headers.update({"Set-Cookie": next(itervalues(session_cookie)).OutputString()})

            self.logger.debug("Assigned incoming HttpEvent cookie '{key}' value of '{value}'".format(key=self.cookie_key,
                                                                                                     value=session_cookie['session']), event=event)

            self.send_event(event)
        except Exception as err:
            self.logger.error("Unable to assign cookie: {err}".format(err=err), event=event)
            self.send_error(event)

# TODO: Implement static routed "CheckCookie" that routes based on cookie presence and value
# TODO: Implement expiry in value reading