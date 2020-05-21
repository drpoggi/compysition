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
import socket
import abc

pickle = None
try:
    import cPickle as pickle #Python 2
except ImportError:
    import _pickle as pickle #Python 3

from gevent.queue import Queue

from compysition.actor import Actor
from future.utils import with_metaclass

DEFAULT_PORT = 9000

#TODO: Will be simple to implement ZMQDealer, ZMQREQ, ZMQREP, but the abstract bases may morph during implementations


class _ZMQContextSharer(abc.ABCMeta):

    """
    This metaclass is designed to hold a shared context across multiple instances for use by the ZeroMQ 'inproc' protocol.
    As inproc will only work inside of a single interpretor instance, so to will this shared_context
    """

    def __init__(cls, *args, **kwargs):
        if not hasattr(cls, 'shared_context'):
            cls.shared_context = zmq.Context()

        super(_ZMQContextSharer, cls).__init__(*args, **kwargs)

class _ZMQ(with_metaclass(_ZMQContextSharer, Actor)):

    """
    **Abstract base for ZMQ objects**

    Parameters:
        name (str):
            | The instance name
        port (Optional[int]):
            | The port for the ZeroMQ socket to connect or bind to
            | Default: 9000
        host (Optional[str]):
            | The host for the ZeroMQ socket to connect or bind to
            | Default: Attempts to resolve local host name via socket.gethostbyname(socket.gethostname())
        mode (Optional[str]):
            | The mode for the socket to use. (bind|connect)
            | Default: connect

    Abstract Properties:
        protocol (zmq.PROTOCOL)
            | The ZermMQ protocol for an implementing class to connect with.
            | (zmq.PUSH, zmq.PULL, zmq.DEALER, zmq.ROUTER, zmq.REQ, zmq.REP, zmq.SUB, zmq.PUB, etc)

    """

    TCP = "tcp"
    IPC = "ipc"
    INPROC = "inproc"

    @abc.abstractproperty
    def protocol(self):
        return self._protocol

    @protocol.setter
    def protocol(self, protocol):
        self._protocol = protocol

    def __init__(self, name, port=DEFAULT_PORT, transmission_protocol=TCP, socket_file=None, host=None, mode="connect", *args, **kwargs):
        super(_ZMQ, self).__init__(name, *args, **kwargs)
        self.blockdiag_config["shape"] = "cloud"
        self.port = port
        self.host = host or socket.gethostbyname(socket.gethostname())
        self.mode = mode

        self.format_connection = {self.TCP: "tcp://{0}:{1}".format(self.host, port),
                                    self.IPC: "ipc://{0}".format(socket_file),
                                    self.INPROC: "inproc://{0}".format(socket_file)}

        if transmission_protocol in self.format_connection:
            self.transmission_protocol = transmission_protocol
        else:
            raise ValueError("Transmission protocol must be in {0}".format(self.format_connection.keys()))

        self.socket_file = socket_file

        self.socket = self.create_socket(context=self.context)

    @property
    def context(self):
        if self.transmission_protocol == self.INPROC:
            return self.shared_context
        else:
            return zmq.Context()

    def create_socket(self, context=None):
        context = context or zmq.Context()
        _socket = context.socket(self.protocol)

        if self.mode == "connect":
            _socket.connect(self.format_connection[self.transmission_protocol])
        elif self.mode == "bind":
            _socket.bind(self.format_connection[self.transmission_protocol])

        return _socket


class _ZMQOut(_ZMQ):

    """
    **A still-abstract implementation of _ZMQ base that is designed for an event being SENT over ZeroMQ**
    """

    def __init__(self, name, mode="connect", *args, **kwargs):
        super(_ZMQOut, self).__init__(name, mode=mode, *args, **kwargs)
        self.outbound_queue = Queue()

    def consume(self, event, *args, **kwargs):
        self.outbound_queue.put(event)

    def pre_hook(self):
        self.threads.spawn(self.__consume_outbound_queue)

    def __consume_outbound_queue(self):
        while self.loop():
            try:
                event = self.outbound_queue.get(timeout=2.5)
            except Exception:
                event = None

            if event is not None:
                try:
                    self.socket.send(pickle.dumps(event))
                except Exception as err:
                    self.logger.error("Unable to send event over ZMQ: {err}".format(err=err), event=event)


class _ZMQIn(_ZMQ):

    """
    **A still-abstract implementation of _ZMQ base that is designed for an event being RECEIVED over ZeroMQ**
    """

    def __init__(self, name, mode="bind", *args, **kwargs):
        super(_ZMQIn, self).__init__(name, mode=mode, *args, **kwargs)
        self.poller = zmq.Poller()
        self.poller.register(self.socket, zmq.POLLIN)

    def pre_hook(self):
        self.threads.spawn(self._listen)

    def consume(self, event, *args, **kwargs):
        self.logger.warning("Received event on queue, but this actor does not consume. Event has been discarded", event=event)

    def _listen(self):
        while self.loop():
            try:
                items = self.poller.poll()
            except KeyboardInterrupt:
                break

            if items:
                event = self.socket.recv_multipart()
                event = pickle.loads(event[0])
                self.send_event(event)


class ZMQPush(_ZMQOut):

    """
    **Send events over ZMQ Push**
    """

    protocol = zmq.PUSH


class ZMQPull(_ZMQIn):

    """
    **Receive events over ZMQ Pull**
    """

    protocol = zmq.PULL
