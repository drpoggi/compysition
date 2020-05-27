from __future__ import absolute_import

from compysition.actor import Actor
from compysition.event import JSONEvent, XMLEvent
from compysition.errors import MalformedEventData
from compysition.util import iterkeys

class XMLToDict(Actor):

    """
    **Actor implementation of the dicttoxml lib. Converts an incoming dictionary to XML**


    Input:
        XMLEvent
    Output:
        JSONEvent

    Parameters:
        name (str)
            | The actor instance Name

        flatten (Optional[bool])
            | If true, the root element of the incoming XML will be stripped out, as a root
            | node is not a requirement for a json object. If the root node is 'jsonify_envelope' then this value will be ignored
            | and always stripped (a functionality that can be found on the internal event conversion logic)
    """

    input = XMLEvent
    output = JSONEvent

    def __init__(self, name, flatten=False, *args, **kwargs):
        self.flatten = flatten
        super(XMLToDict, self).__init__(name, *args, **kwargs)

    def consume(self, event, *args, **kwargs):
        try:
            event = event.convert(JSONEvent)
            if self.flatten:
                event.data = event.data[next(iterkeys(event.data))]
        except Exception as err:
            self.logger.error("Unable to convert to XML: {0}".format(err), event=event)
            raise MalformedEventData(err.message)
        else:
            self.logger.info("Successfully converted XML to Dict", event=event)
            self.send_event(event)
