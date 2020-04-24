import json
import xmltodict
from lxml import etree
from xml.sax.saxutils import XMLGenerator
from xml.parsers import expat

'''
	All objects in this file are intended for Event classes only
'''

__all__ = [
	"_InternalJSONXMLConverter",
	"_decimal_default",
	"_should_force_list",
	"_NullLookupValue",
	"_UnescapedDictXMLGenerator"
]

_internal_json_envelope_tag = "jsonified_envelope"
_internal_envelope_tags = [_internal_json_envelope_tag]

class _InternalJSONXMLConverter():
    @staticmethod
    def to_xml(json):
        ####### Desired
        #if len(json) == 0:
        #    return etree.Element(_internal_json_envelope_tag)
        ####### Current
        #######
        if isinstance(json, list) or len(json) > 1:
            json = {_internal_json_envelope_tag: json}
        _, value = next(json.iteritems())
        if isinstance(value, list):
            json = {_internal_json_envelope_tag: json}
        return etree.fromstring(xmltodict.unparse(json).encode('utf-8'))

    @staticmethod
    def to_json(xml):
        json = xmltodict.parse(etree.tostring(xml), expat=expat, force_list=_should_force_list)
        if len(json) == 1 and isinstance(json, dict):
            key, value = next(json.iteritems())
            if key in _internal_envelope_tags:
                ####### Desired
                #json = {} if value is None else value
                ####### Current
                json = value
                #######
        return json

class _NullLookupValue(object):

    def get(self, key, value=None):
        return self

class _UnescapedDictXMLGenerator(XMLGenerator):
    """
    Simple class designed to enable the use of an unescaped functionality
    in the event that dictionary value data is already XML
    """

    def characters(self, content):
        try:
            if content.lstrip().startswith("<"):
                etree.fromstring(content)
                self._write(content)
            else:
                XMLGenerator.characters(self, content)
        except (AttributeError, ValueError, etree.XMLSyntaxError, Exception):
            #TODO could be more specific on errors caught
            XMLGenerator.characters(self, content)

def _decimal_default(obj):
    """ Lets us pass around Decimal type objects and not have to worry about doing conversions in the individual actors"""
    if isinstance(obj, Decimal):
        return float(obj)
    raise TypeError

def _should_force_list(path, key, value):
    """
    This is a callback passed to xmltodict.parse which checks for an xml attribute force_list in the XML, and if present
    the outputted JSON is an list, regardless of the number of XML elements. The default behavior of xmltodict is that
    if there is only one <element>, to output as a dict, but if there are multiple then to output as a list. @force_list
    is useful in situations where the xml could have 1 or more <element>'s, but code handling the JSON elsewhere expects
    a list.

    For example, if you have an XSLT that produces 1 or more items, you could have the resulting output of the XSLT
    transformation be (note we only need to set force_list on the first node, the rest will automatically be appended):
        <xsl:if test="position() = 1">
            <transactions force_list=True>
                <amount>85</amount>
            </transactions>
        </xsl:if>

    and the JSON output will be:
        {"transactions" : [
            "amount": "85"
            ]
        }
    whereas the default when the @force_list attribute is not present would be:
        {"transactions": {
            "amount": "85"
            }
        }

    which could break code handling this JSON which always expects "transactions" to be a list.
    """
    if isinstance(value, dict) and '@force_list' in value:
        # pop attribute off so that it doesn't get included in the response
        value.pop('@force_list')
        return True
    else:
        return False