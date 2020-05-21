from compysition.queue import Queue, QueueEmpty
from compysition.util import iteritems

class FunneledQueue(Queue):

    """
    This class exists to make it easier for us to check any and all actor output for any queues registered with the funnel_queue
    """

    def __init__(self, name, funnel_queue=None, *args, **kwargs):
        self.funnel_queue = funnel_queue
        super(FunneledQueue, self).__init__(name, *args, **kwargs)

    def put(self, element, *args, **kwargs):
        if self.funnel_queue:
                self.funnel_queue.put(element)
        super(FunneledQueue, self).put(element, *args, **kwargs)


class _TestActorWrapper(object):

    def __init__(self, actor, input_queues=["inbox"], output_queues=["outbox"], error_queues=["error"], output_timeout=5):
        self.actor = actor
        self.output_timeout = output_timeout

        self.input_queues = self._setup_pool(input_queues)
        self._output_funnel = Queue("output_funnel")
        self._error_funnel = Queue("error_funnel")

        self.output_queues = self._setup_pool(output_queues, queue_class=FunneledQueue, queue_kwargs={"funnel_queue": self._output_funnel})
        self.error_queues = self._setup_pool(error_queues, queue_class=FunneledQueue, queue_kwargs={"funnel_queue": self._error_funnel})
        self.__output_funnel = Queue("outbound_funnel")
        self.__error_funnel = Queue("outbound_funnel")

        for queue_name, queue in iteritems(self.input_queues):
            self.actor.register_consumer(queue_name, queue)

        for queue_name, queue in iteritems(self.output_queues):
            self.actor.pool.outbound.add(queue_name, queue=queue)

        for queue_name, queue in iteritems(self.error_queues):
            self.actor.pool.error.add(queue_name, queue=queue)

        self.actor.start()

    def _setup_pool(self, queue_names, queue_class=Queue, queue_kwargs=None):
        queue_kwargs = queue_kwargs or {}
        if not isinstance(queue_names, list):
            queue_names = [queue_names]

        return {queue: queue_class(queue, **queue_kwargs) for queue in queue_names}

    @property
    def input(self):
        return self._input

    @input.setter
    def input(self, _input):
        self._input = _input
        self.actor.send_event(_input, queues=self.input_queues, check_output=False)

    @property
    def output(self):
        try:
            return self._output_funnel.get(block=True, timeout=self.output_timeout)
        except QueueEmpty:
            # if we failed to get output queue, try dumping what's in the error queue
            # will fail but gives more information about why
            error = self._error_funnel.get(block=True, timeout=self.output_timeout)
            print('ERROR: {}'.format(error))
            return error

    @property
    def error(self):
        return self._error_funnel.get(block=True, timeout=self.output_timeout)

    def stop(self):
        self.actor.stop()