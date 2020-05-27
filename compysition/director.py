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

import signal
import os
import traceback

from gevent import signal_handler, event

from compysition.actor import Actor
from compysition.actors import Null, STDOUT, EventLogger
from compysition.util import iteritems, itervalues

class Director(object):

    _async_class = event.Event

    def __init__(self, size=500, name="default", generate_blockdiag=False, blockdiag_dir="./build/blockdiag"):
        signal_handler(signal.SIGINT, self.stop)
        signal_handler(signal.SIGTERM, self.stop)

        self.name = name
        self.actors = {}
        self.size = size

        self.log_actor = self.__create_actor(STDOUT, "default_stdout")
        self.error_actor = self.__create_actor(EventLogger, "default_error_logger")

        self.__running = False
        self.__block = self._async_class()
        self.__block.clear()

        self.blockdiag_dir = blockdiag_dir
        self.generate_blockdiag = generate_blockdiag
        if generate_blockdiag:
            self.blockdiag_out = """diagram admin {\n"""

    def get_actor(self, name):
        actor = self.actors.get(name, None)
        if not actor:
            if self.log_actor.name == name:
                return self.log_actor
            elif self.error_actor.name == name:
                return self.error_actor
        else:
            return actor

    def connect_log_queue(self, source, destination, *args, **kwargs):
        self.connect_queue(source, destination, connect_function="connect_log_queue", *args, **kwargs)

    def connect_error_queue(self, source, destination, *args, **kwargs):
        self.connect_queue(source, destination, connect_function="connect_error_queue", *args, **kwargs)

    def connect_queue(self, source, destinations, connect_function="connect_queue", *args, **kwargs):
        '''**Connects one queue to the other.**

        There are 2 accepted syntaxes. Consider the following scenario:
            director    = Director()
            test_event  = director.register_actor(TestEvent,  "test_event")
            std_out     = director.register_actor(STDOUT,     "std_out")

        First accepted syntax
            Queue names will default to the name of the source for the destination actor,
                and to the name of the destination for the source actor
            director.connect_queue(test_event, std_out)

        Second accepted syntax
            director.connect_queue((test_event, "custom_outbox_name"), (stdout, "custom_inbox_name"))

        Both syntaxes may be used interchangeably, such as in:
            director.connect_queue(test_event, (stdout, "custom_inbox_name"))
        '''
        #TODO: This is currently unsupported (weird formatting to hook into pycharm 'TODO' tracker)
        '''
            director.connect_queue((test_event, "custom_outbox_name"), [actor_one, actor_two]).

            This is due to the way that queue 'keying' is done. I would like to modify the logic for queue connection
            on the actors in the future to allow this. Probably by removing the 'name' attribute from a queue altogether,
            and having the 'name' exist solely as a key on QueuePool, or the actor, which can link to a list of queues
            as well as a single queue. This would use the same "send_event" logic, but allowing the key to be used as
            an alias to a specific set of queues.
        '''

        if not isinstance(destinations, list):
            destinations = [destinations]

        (source_name, source_queue_names) = self._parse_connect_arg(source)
        source = self.get_actor(source_name)

        if not isinstance(source_queue_names, list):
            source_queue_names = [source_queue_names]

        for source_queue_name in source_queue_names:
            for destination in destinations:
                (destination_name, destination_queue_name) = self._parse_connect_arg(destination)
                destination = self.get_actor(destination_name)
                if self.generate_blockdiag:
                    self.blockdiag_out += "{0} -> {1};\n".format(source.name, destination.name)

                if destination_queue_name is None:
                    if source_queue_name is None:
                        destination_queue_name = source.name
                    else:
                        destination_queue_name = source_queue_name

                if source_queue_name is None:
                    destination_source_queue_name = destination.name
                else:
                    destination_source_queue_name = source_queue_name

                getattr(source, connect_function)(source_queue_name=destination_source_queue_name, destination=destination, destination_queue_name=destination_queue_name, *args, **kwargs)

    def _parse_connect_arg(self, input):
        if isinstance(input, tuple):
            (actor, queue_name) = input
            if isinstance(actor, Actor):
                actor_name = actor.name
        elif isinstance(input, Actor):
            actor_name = input.name
            queue_name = None                # Will have to be generated deterministically

        return (actor_name, queue_name)

    def finalize_blockdiag(self):
        #TODO: Make this into an object pattern
        img_dir = "{0}{1}img".format(self.blockdiag_dir, os.sep)
        self.blockdiag_out += "\n}"

        try:
            if not os.path.exists(img_dir):
                os.makedirs(img_dir)
            from blockdiag.command import BlockdiagApp
            with open("{0}{1}{2}.diag".format(self.blockdiag_dir, os.sep, self.name),'w') as f:
                f.write(self.blockdiag_out)
            BlockdiagApp().run(["{0}{1}{2}.diag".format(self.blockdiag_dir, os.sep, self.name),
                                "-Tsvg",
                                "-o",
                                "{0}{1}img{1}{2}.svg".format(self.blockdiag_dir, os.sep, self.name)])
        except Exception as err:
            print("Unable to write blockdiag: {err}".format(err=traceback.format_exc()))

    def register_actor(self, actor, name=None, *args, **kwargs):
        if not isinstance(actor, Actor):
            actor = self.__create_actor(actor, name, *args, **kwargs)


        self.actors[actor.name] = actor
        if self.generate_blockdiag:
            self.blockdiag_out += "{0} [".format(actor.name)
            for key, value in iteritems(actor.blockdiag_config):
                self.blockdiag_out += "{0} = \"{1}\"".format(key, value)
            self.blockdiag_out += "]\n"
        return actor

    def register_log_actor(self, actor, name, *args, **kwargs):
        """Initialize a log actor for the director instance"""
        self.log_actor = self.__create_actor(actor, name, *args, **kwargs)
        return self.log_actor

    def register_error_actor(self, actor, name, *args, **kwargs):
        self.error_actor = self.__create_actor(actor, name, *args, **kwargs)
        return self.error_actor

    def __create_actor(self, actor, name, *args, **kwargs):
        return actor(name, size=self.size, *args, **kwargs)

    def _setup_default_connections(self):
        '''Connect all log, metric, and error queues to their respective actors'''

        for actor in itervalues(self.actors):
            if self.error_actor:
                try:
                    if len(actor.pool.error) == 0:
                        self.connect_error_queue(actor, self.error_actor)
                except Exception as err:
                    print(err)

            actor.connect_log_queue(source_queue_name="logs", destination=self.log_actor, check_existing=False)

        self.log_actor.connect_log_queue(source_queue_name="logs", destination=self.log_actor, check_existing=False)
        self.error_actor.connect_log_queue(source_queue_name="logs", destination=self.log_actor, check_existing=False)

    def is_running(self):
        return self.__running

    def start(self, block=True):
        '''Starts all registered actors.'''
        self.__running = True
        self._setup_default_connections()

        for actor in itervalues(self.actors):
            actor.start()

        self.log_actor.start()
        self.error_actor.start()

        if self.generate_blockdiag:
            self.finalize_blockdiag()
        if block:
            self.block()

    def block(self):
        '''Blocks until stop() is called.'''
        self.__block.wait()

    def stop(self):
        '''Stops all input actors.'''

        for actor in itervalues(self.actors):
            actor.stop()

        self.log_actor.stop()
        self.__running = False
        self.__block.set()
