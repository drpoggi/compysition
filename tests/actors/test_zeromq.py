import random
import unittest

from compysition.actors.zeromq import ZMQPush, ZMQPull
from compysition.event import JSONEvent, XMLEvent
from compysition.testutils.test_actor import _TestActorWrapper
from compysition.util import get_uuid

class TestPushPullIPC(unittest.TestCase):

    def setUp(self):
        socket = "/tmp/{0}.sock".format(get_uuid())
        self.push = _TestActorWrapper(ZMQPush("zmqpush", socket_file=socket, transmission_protocol=ZMQPush.IPC))
        self.pull = _TestActorWrapper(ZMQPull("zmqpull", socket_file=socket, transmission_protocol=ZMQPull.IPC))

    def test_push_json_event(self):
        data = {"foo": "barjson"}
        _input = JSONEvent(data=data)
        self.push.input = _input
        _output = self.pull.output
        self.assertEqual(_output.data_string(), _input.data_string())
        self.assertEqual(_output.event_id, _input.event_id)
        self.assertEqual(_output.meta_id, _input.meta_id)

    def test_push_xml_event(self):
        data = "<foo>barxml</foo>"
        _input = XMLEvent(data=data)
        self.push.input = _input
        _output = self.pull.output
        self.assertEqual(_output.data_string(), _input.data_string())
        self.assertEqual(_output.event_id, _input.event_id)
        self.assertEqual(_output.meta_id, _input.meta_id)


class TestZMQPushPullTCP(TestPushPullIPC):

    def setUp(self):
        port = random.randint(8000, 9000)       # This DOES have a 1/1000 chance of self collision
        self.push = _TestActorWrapper(ZMQPush("zmqpush", port=port))
        self.pull = _TestActorWrapper(ZMQPull("zmqpull", port=port))


class TestZMQPushPullINPROC(TestPushPullIPC):

    def setUp(self):
        socket = "/tmp/{0}.sock".format(get_uuid())
        self.push = _TestActorWrapper(ZMQPush("zmqpush", socket_file=socket, transmission_protocol=ZMQPush.INPROC))
        self.pull = _TestActorWrapper(ZMQPull("zmqpull", socket_file=socket, transmission_protocol=ZMQPull.INPROC))