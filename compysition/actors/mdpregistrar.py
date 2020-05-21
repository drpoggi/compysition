#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
#  mdpregistrar.py
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

import gevent
import zmq.green as zmq
import time

from .util import mdpdefinition as MDPDefinition
from .util.mdpregistrar import HeartbeatManager, RegistrationService, Broker
from compysition.actor import Actor
from compysition.util import iteritems

class MDPBrokerRegistrationService(Actor, RegistrationService):
    """
    This service is the standalone service the brokers configuration notification between active brokers and clients, so that the clients can round-robin between brokers to evenly
    distribute load. Implementors of this service should use the 'BrokerRegistrator' class on the broker end, and the 'RegistrationServiceListener' class on the client end to register or listen for 
    registration updates, respectively
    """

    timeout = 2500
    receiver_socket = None
    client_publisher_socket = None
    poller = None
    brokers = None
    heartbeat_manager = None

    def __init__(self, name, listen_port=None, publish_port=None, *args, **kwargs):

        Actor.__init__(self, name, *args, **kwargs)
        RegistrationService.__init__(self, *args, **kwargs)
        self.brokers = {}

        if listen_port is not None:
            self.registration_service_port = listen_port

        if publish_port is not None:
            self.registration_publisher_port = publish_port

        self.receiver_socket = self.context.socket(zmq.ROUTER)
        self.receiver_socket.bind("tcp://*:{0}".format(self.registration_service_port))

        self.client_publisher_socket = self.context.socket(zmq.PUB)
        self.client_publisher_socket.bind("tcp://*:{0}".format(self.registration_publisher_port))

        gevent.sleep(0.1) # Make sure publisher has time to fully connect. This is a zmq nuance
        
        #self.heartbeat_manager = HeartbeatManager(heartbeat_interval=self.timeout)
        self.poller = zmq.Poller()
        self.poller.register(self.receiver_socket, zmq.POLLIN)

    def send_to_clients(self, command, msg):
        self.client_publisher_socket.send_multipart(self.format_message(command, msg))

    def format_message(self, command, msg):
        """
        Simply a wrapper to control the syntax of the message broadcast to clients, for consistency
        """
        if not isinstance(msg, list):
            msg = [msg]

        message = [self.manager_subscriber_scope, '', command] + msg
        return message

    def forward_broker_heartbeats(self, broker=None):
        """
        Compile the message for the heartbeat manager to send to the clients, and send the broker heartbeat
        """
        
        if broker is None:
            if(len(self.brokers) > 0):
                message = []     
                for broker_identity, broker in iteritems(self.brokers):
                    message.extend([broker_identity, broker.port])

                self.heartbeat_manager.send_heartbeats(self.client_publisher_socket, self.format_message(MDPDefinition.B_HEARTBEAT, message))
        else:
            self.send_to_clients(MDPDefinition.B_HEARTBEAT, [broker.identity, broker.port])


    def check_broker_liveness(self):
        """
        Check if a broker has not sent a heartbeat within the HEARTBEAT_INTERVAL timeframe. Reduce 'liveness' on the broker object by 1 for each occurrence, until liveness reaches 0.
        Liveness reaching 0 results in an immediate disconnect notification being sent to all clients
        """
        broker_keys = self.brokers.keys()
        for broker_identity in broker_keys:
            broker = self.brokers[broker_identity]
            if time.time() > broker.expiration_time:
                broker.liveness -= 1
                if broker.liveness == 0:
                    self.disconnect_broker(broker_identity)

    def disconnect_broker(self, broker_identity):
        """
        Broadcast an immediate disconnect notification to all subscribed clients for a disconnected broker, and delete the broker from the internal dictionary
        """
        broker = self.brokers[broker_identity]
        self.send_to_clients(MDPDefinition.B_DISCONNECT, [broker_identity, broker.port])
        self.logger.info("Notifying clients that broker {0} has disconnected".format(broker_identity))
        del self.brokers[broker_identity]

    def start_service(self):
        """
        The main work of the service is done here - poll for incoming messages, and initiate liveness checks
        heartbeat broadcasts
        """
        while self.loop():
            items = self.poller.poll(self.timeout)
            if items:
                message = self.receiver_socket.recv_multipart()
                if not len(message) >= 3:
                    # On production we very occasionally seem to receive an invalid message from the broker, in which
                    # case we just want to ignore it and move on to listening for the next message.
                    self.logger.error('Received an invalid message from the broker: {msg}'.format(msg=message))
                    continue

                sender = message.pop(0)
                empty = message.pop(0)
                port = message.pop(0)

                sender_identity = sender

                broker = self.brokers.get(sender_identity)

                if broker is None:
                    broker = Broker(sender_identity, port)
                    self.brokers[sender_identity] = broker
                    self.logger.info("Registered new broker [{0}] on port {1}".format(sender, port))
                else:
                    broker.refresh_expiration_time()

                self.forward_broker_heartbeats(broker=broker)

            self.check_broker_liveness()
            #self.forward_broker_heartbeats()

    def pre_hook(self):
        gevent.spawn(self.start_service)

    def consume(self, event, *arsg, **kwargs):
        pass
