#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  mdpactors.py
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

import zmq.green as zmq
import gevent
import traceback

pickle = None
try:
    import cPickle as pickle #Python 2
except ImportError:
    import _pickle as pickle #Python 3

import abc

from gevent.queue import Queue #TODO Don't need this AND the generic gevent import
from uuid import uuid4 as uuid

from .util.mdpregistrar import BrokerManager #TODO Fix Redundancy?
from .util import mdpdefinition as MDPDefinition
from compysition.actor import Actor

"""
The MDPWorker and MDPClient are implementations of the ZeroMQ MajorDomo configuration, which deals with dynamic process routing based on service configuration and registration.

Also required for this implementation to function is a process or actor running a RegistrationService and one or more MDPBrokers

TODO: Frame documentation. Create helper class to parse frames!!!!!!!!!!!!!!!!!!!!!!!!!
"""

class MDPActor(Actor):

    __metaclass__ = abc.ABCMeta

    """
    Receive or send events over ZMQ
    """

    context = None
    broker_manager = None
    socket_identity = None
    outbound_queue = None

    def __init__(self, name, service_prefix="", service_postfix="", *args, **kwargs):
        super(MDPActor, self).__init__(name, *args, **kwargs)
        self.blockdiag_config["shape"] = "cloud"
        self.socket_identity = uuid().get_hex()
        self.context = zmq.Context()
        self.outbound_queue = Queue()
        self.broker_manager = BrokerManager(controller_identity=self.socket_identity, logger=self.logger, *args, **kwargs)
        self.service_prefix = service_prefix
        self.service_postfix = service_postfix

    def pre_hook(self):
        self.threads.spawn(self.__listen)
        self.threads.spawn(self.__consume_outbound_queue)
        self.threads.spawn(self.verify_brokers)

    def consume(self, event, *args, **kwargs):
        self.outbound_queue.put(event)

    def __consume_outbound_queue(self):
        while self.loop():
            try:
                event = self.outbound_queue.get(timeout=2.5)
            except Exception:
                event = None

            if event is not None:
                broker = self.broker_manager.get_next_broker_in_queue()
                if broker is None:
                    self.outbound_queue.put(event)
                    self.logger.error("There are events waiting on the client queue, but no brokers are registered. Queue size is {0}".format(
                        self.outbound_queue.qsize()), event=event)
                    gevent.sleep(1)         # Place back on queue and wait for a broker
                else:
                    self.send_outbound_message(broker.outbound_socket, event)

            self.send_heartbeats()

    def __listen(self):
        while self.loop():
            try:
                polled_sockets = dict(self.broker_manager.inbound_poller.poll())
            except KeyboardInterrupt:
                break

            if polled_sockets:
                message = None

                for socket_tuple in self.broker_manager.inbound_poller.sockets:
                    inbound_socket, poll_type = socket_tuple
                    if inbound_socket is not None:
                        if polled_sockets.get(inbound_socket) == zmq.POLLIN:
                            message = inbound_socket.recv_multipart()
                            break

                self.process_inbound_message(message, origin_broker=inbound_socket.broker)

    @abc.abstractmethod
    def send_outbound_message(self, socket, event):
        """
        Args:
            socket: (zmq.Socket) Socket with which to send the message
            event:  (compysition.event.Event) The event to send

        Returns:
            None
        """
        pass

    @abc.abstractmethod
    def process_inbound_message(self, message, *args, **kwargs):
        """
        Args:
            message:    The inbound message to process
            *args:
            **kwargs:

        Returns:
            None
        """
        pass

    @abc.abstractmethod
    def verify_brokers(self):
        """
        Sends verification requests to connected brokers

        Returns:
            None
        """
        pass

    @abc.abstractmethod
    def send_heartbeats(self):
        """
        Sends heartbeats to connected brokers

        Returns:
            None
        """
        pass


class MDPClient(MDPActor):

    client = None

    def __init__(self, name, *args, **kwargs):
        super(MDPClient, self).__init__(name, *args, **kwargs)

    def send_outbound_message(self, socket, event):
        try:
            request_id = event.meta_id                  # Set for broker logging so we can trace the path of an event easily
            service = b"{0}".format(self.service_prefix + event.service + self.service_postfix)
            self.logger.info("Sending event to service '{0}'".format(service), event=event)
            message = [request_id, b"{0}".format(pickle.dumps(event, -1))]
            self.send(service, message, broker_socket=socket)
        except Exception as err:
            self.logger.error("Unable to find necessary chains: {0}".format(traceback.format_exc()))

    def verify_brokers(self):
        while self.loop():
            self.broker_manager.send_verification_requests(MDPDefinition.C_CLIENT)
            gevent.sleep(1)

    def process_inbound_message(self, message, *args, **kwargs):
        if message:
            assert len(message) >= 3
                
            empty = message.pop(0)
            header = message.pop(0)
            assert MDPDefinition.C_CLIENT == header

            command = message.pop(0)

            if command == MDPDefinition.B_HEARTBEAT:
                self.logger.info("Got heartbeat: {0}".format(message))
            elif command == MDPDefinition.B_VERIFICATION_RESPONSE:
                self.logger.info("Received Verification Response from {0}".format(message))
                self.broker_manager.verify_broker(message.pop(0))
            elif command == MDPDefinition.W_REPLY:
                empty = message.pop(0)
                request_identity = message.pop(0)

                event = pickle.loads(message[0])

                self.logger.info("Received reply from broker", event=event)
                self.send_event(event)

    def set_broker(self, broker_socket=None):
        if broker_socket is not None:
            self.broker_socket = broker_socket

    def send(self, service, request, command=None, broker_socket=None, *args, **kwargs):
        command = command or kwargs.get('command', None) or MDPDefinition.C_REQUEST
        broker_socket = broker_socket or kwargs.get('broker_socket', None)
        if broker_socket is not None:
            """Send request to broker
            """
            if not isinstance(request, list):
                request = [request]

            # Prefix request with protocol frames
            # Frame 0: empty (REQ emulation)
            # Frame 1: "MDPCxy" (six bytes, MDP/Client x.y)
            # Frame 2: Command (See MDPDefinition)
            # Frame 3: Service name (printable string)

            request = ['', MDPDefinition.C_CLIENT, command, service] + request
            broker_socket.send_multipart(request)

    def send_heartbeats(self):
        pass

class MDPWorker(MDPActor):

    service = None
    requests = None

    def __init__(self, name, service, *args, **kwargs):
        super(MDPWorker, self).__init__(name, *args, **kwargs)
        self.service = service
        self.requests = {}

    def verify_brokers(self):
        while self.loop():
            self.broker_manager.send_verification_requests(MDPDefinition.W_WORKER, message=self.service)
            gevent.sleep(1)

    def process_inbound_message(self, message, *args, **kwargs):
        origin_broker = kwargs.get('origin_broker', None) or None
        if message is not None:
            assert len(message) >= 3

            empty = message.pop(0)
            assert empty == ''

            header = message.pop(0)
            assert header == MDPDefinition.W_WORKER

            command = message.pop(0)
            if command == MDPDefinition.W_REQUEST:
                return_address = message.pop(0)
                empty = message.pop(0)
                broker_event_logging_id = message.pop(0)
                event = pickle.loads(message.pop(0))

                request_id = event.event_id
                self.requests[request_id] = Request(return_address, origin_broker)
                self.send_event(event)

            elif command == MDPDefinition.B_VERIFICATION_RESPONSE:
                self.logger.info("Received Verification Response from {0}".format(message))
                self.broker_manager.verify_broker(message.pop(0))
            elif command == MDPDefinition.W_HEARTBEAT:
                # Do nothing for heartbeats
                pass
            elif command == MDPDefinition.W_DISCONNECT:
                self.logger.info("Received disconnect command from {0}".format(message))
                self.broker_manager.disconnect_broker(origin_broker.identity)
            else:
                pass

    def send_outbound_message(self, socket, event):
        request_id = event.event_id
        request = self.requests.get(request_id)
        if request is not None:
            broker = request.origin_broker
            return_address = request.return_address
            broker_event_logging_id = event.meta_id
            try:
                message = ['', MDPDefinition.W_WORKER, MDPDefinition.W_REPLY, return_address, '', str(broker_event_logging_id), b"{0}".format(pickle.dumps(event, -1))]
            except Exception as err:
                self.logger.error(err, event=event)

            if broker is not None:                  # Prioritize the originating broker first
                try:
                    broker.outbound_socket.send_multipart(message)
                    self.logger.info("Sent reply through originating broker", event=event)
                except zmq.ZMQError:
                    socket.send_multipart(message)  # Use the current broker in the round-robin rotation
                    self.logger.info("Sent reply through non-originating broker", event=event)
        else:
            self.logger.error("Received event response but was unable to find client return address for id {0}".format(request_id), event=event)

    def send_heartbeats(self):
        self.broker_manager.send_heartbeats(message=['', MDPDefinition.W_WORKER, MDPDefinition.W_HEARTBEAT, self.socket_identity])


class Request(object):

    return_address = None       # The socket id of the originating client
    origin_broker = None        # The original broker this message was received through

    def __init__(self, return_address, origin_broker):
        self.return_address = return_address
        self.origin_broker = origin_broker
