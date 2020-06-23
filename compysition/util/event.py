import json
import xmltodict
from lxml import etree
from xml.sax.saxutils import XMLGenerator
from xml.parsers import expat
from collections import OrderedDict
from decimal import Decimal
import urllib

from . import ignore

'''
    All objects in this file are intended for Event classes only
'''

__all__ = [
    "_XWWWFormList",
    "_InternalJSONXMLConverter",
    "_InternalXWWWFORMXMLConverter",
    "_InternalXWWWFORMJSONConverter",
    "_decimal_default",
    "_should_force_list",
    "_NullLookupValue",
    "_UnescapedDictXMLGenerator"
]

_internal_json_envelope_tag = "jsonified_envelope"
_internal_xwwwform_envelope_tag = "x_www_form_envelope"
_internal_envelope_tags = [_internal_json_envelope_tag, _internal_xwwwform_envelope_tag]

class _XWWWFormList(list): pass #used to distinguish XWWWForm list from standard lists

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

class _InternalXWWWFORMXMLConverter():

    @staticmethod
    def _single_to_xml(key, value):
        with ignore(ValueError, etree.XMLSyntaxError):
            return etree.fromstring(value)
        xml_str = "<{0}>{1}</{0}>".format(key, value) if len(value) > 0 else "<{}/>".format(key)
        return etree.fromstring(xml_str)

    @staticmethod
    def _explode_obj(xwwwform):
        key, values = next(xwwwform.iteritems())
        for value in values:
            yield key, value

    @staticmethod
    def to_xml(xwwwform):
        obj_count = len(xwwwform)
        if obj_count != 1 or (obj_count == 1 and len(next(xwwwform[0].iteritems())[1]) > 1):
            root = etree.Element(_internal_xwwwform_envelope_tag)
            for obj in xwwwform:
                for key, value in _InternalXWWWFORMXMLConverter._explode_obj(obj):
                    root.append(_InternalXWWWFORMXMLConverter._single_to_xml(key, value))
            return root
        key, values = next(xwwwform[0].iteritems())
        return _InternalXWWWFORMXMLConverter._single_to_xml(key, values[0])

    @staticmethod
    def _single_to_xwwwform(xml):
        text = "" if xml.text is None else xml.text
        num_childs = len(xml.getchildren())
        if len(xml.attrib) > 0 or num_childs > 1 or (len(text) > 0 and num_childs > 0):
            return etree.tostring(xml)
        elif num_childs > 0:
            return etree.tostring(xml.getchildren()[0])
        return text

    @staticmethod
    def _treat_as_xml(xml):
        cur = {}
        for child in xml.getchildren():
            cur_key, cur_value, child_key, child_value = child.tag, tuple(), child.tag, _InternalXWWWFORMXMLConverter._single_to_xwwwform(child)
            with ignore(StopIteration):
                cur_key, cur_value = next(cur.iteritems())
            if cur_key == child_key:
                cur_value += (child_value,)
                cur[cur_key] = cur_value
            else:
                yield cur_key, cur_value
                cur = {child_key: (child_value,)}
        with ignore(StopIteration):
            yield next(cur.iteritems())

    @staticmethod
    def to_xwwwform(xml):
        treat_as_xml = _InternalXWWWFORMXMLConverter._treat_as_xml
        root = xml if isinstance(xml, etree._Element) else xml.getroot()
        if root.tag in _internal_envelope_tags:
            return _XWWWFormList([{key: value} for key, value in treat_as_xml(root)])
        return _XWWWFormList([{root.tag: (_InternalXWWWFORMXMLConverter._single_to_xwwwform(root),)}])
    
class _InternalXWWWFORMJSONConverter():

    @staticmethod
    def to_json(xwwwform):
        tojson = _InternalXWWWFORMJSONConverter._tojson
        if len(xwwwform) == 0:
            return OrderedDict()
        with ignore(TypeError):
            return [tojson(value) for value in _InternalXWWWFORMJSONConverter._try_unpack_as_list(xwwwform)]
        with ignore(TypeError):
            return OrderedDict([(tojson(key), tojson(value)) for key, value in _InternalXWWWFORMJSONConverter._try_unpack_as_dict(xwwwform)])
        return [{_InternalXWWWFORMJSONConverter._tojson(key): value} for key, value in _InternalXWWWFORMJSONConverter._unpack_as_xwwwform(xwwwform)]

    @staticmethod
    def _try_unpack_as_list(xwwwform):
        for obj in xwwwform:
            key, values = next(obj.iteritems())
            if key not in _internal_envelope_tags:
                raise TypeError
            for value in values:
                yield value

    @staticmethod
    def _unpack_as_xwwwform(xwwwform):
        for obj in xwwwform:
            key, values = next(obj.iteritems())
            values = [_InternalXWWWFORMJSONConverter._tojson(value) for value in values]
            yield key, values

    @staticmethod
    def _try_unpack_as_dict(xwwwform):
        keys = []
        for obj in xwwwform:
            key, values = next(obj.iteritems())
            if key in keys:
                raise TypeError
            keys.append(key)
            if len(values) > 1:
                yield key, list(values)
            else:
                yield key, values[0]

    @staticmethod
    def _treat_as_list(json):
        if isinstance(json, (list, tuple)):
            for l in json:
                yield l
        else:
            yield json

    @staticmethod
    def _try_treat_as_xwwform(json):
        for obj in json:
            for count, (key, value) in enumerate(obj.iteritems(), 1):
                if count > 1:
                    raise TypeError
                yield key, value

    @staticmethod
    def _tostring(data):
        if isinstance(data, (dict, OrderedDict, list)):
            return json.dumps(data)
        return str(data)

    @staticmethod
    def _tojson(data):
        with ignore(TypeError, ValueError):
            return json.loads(data)
        if isinstance(data, (list, tuple)):
            return [_InternalXWWWFORMJSONConverter._tojson(value) for value in data]
        return data

    @staticmethod
    def _tuplify(data):
        return tuple([_InternalXWWWFORMJSONConverter._tostring(actual_value) for actual_value in _InternalXWWWFORMJSONConverter._treat_as_list(data)])

    @staticmethod
    def to_xwwwform(json):
        tostring = _InternalXWWWFORMJSONConverter._tostring
        tuplify = _InternalXWWWFORMJSONConverter._tuplify
        if isinstance(json, (dict, OrderedDict)):
            return _XWWWFormList([{tostring(key): tuplify(value)} for key, value in json.iteritems()])
        try:
            return _XWWWFormList([{tostring(key): tuplify(value)} for key, value in _InternalXWWWFORMJSONConverter._try_treat_as_xwwform(json)])
        except (TypeError, AttributeError) as e:
            return _XWWWFormList([{_internal_json_envelope_tag: tuplify(json)}])

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

class RawXWWWForm:
    @staticmethod
    def unquote(data):
        return urllib.unquote(data.replace('+', ' '))

    @staticmethod
    def quote(data):
        if len(data) > 0:
            return '+'.join([urllib.quote(seg, '') for seg in data.split(' ')])
        return data

    @staticmethod
    def get_values_from_string(data):
        for variable in data.replace(';', '&').split('&'):
            if not variable: continue
            key, value = variable.split('=', 1)
            key = RawXWWWForm.unquote(data=key)
            value = RawXWWWForm.unquote(data=value)
            yield key, value