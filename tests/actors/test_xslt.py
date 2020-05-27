import unittest

from compysition.actors.xslt import XSLT
from compysition.event import XMLEvent
from compysition.errors import MalformedEventData
from compysition.testutils.test_actor import _TestActorWrapper

simple_xslt_case = {
                    "input":    "<root><foo>foo_value</foo><bar>bar_value></bar></root>",
                    "xslt":     """
                                <xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
                                    <xsl:output method="xml"/>

                                    <xsl:template match="@*|node()">
                                        <xsl:copy>
                                            <xsl:apply-templates select="@*|node()"/>
                                        </xsl:copy>
                                    </xsl:template>

                                    <xsl:template match="/*">
                                        <xsl:copy>
                                            <xsl:apply-templates select="@*|node()"/>
                                        </xsl:copy>
                                    </xsl:template>

                                    <xsl:template match="//bar" />

                                </xsl:stylesheet>
                                """,
                    "output":   "<root><foo>foo_value</foo></root>"
                   }

xslt_raised_error_case = {"input": simple_xslt_case["input"],
                          "xslt":   """
                                    <xsl:stylesheet version="1.0" xmlns:xsl="http://www.w3.org/1999/XSL/Transform">
                                        <xsl:output method="xml"/>

                                        <xsl:template match="@*|node()">
                                            <xsl:copy>
                                                <xsl:apply-templates select="@*|node()"/>
                                            </xsl:copy>
                                        </xsl:template>

                                        <xsl:template match="//bar" >
                                            <xsl:message terminate="yes">
                                              <xsl:element name="error">Im raising an exception because I feel like it</xsl:element>
                                            </xsl:message>
                                        </xsl:template>

                                    </xsl:stylesheet>
                                    """,
                          "output": MalformedEventData}


class TestXSLT(unittest.TestCase):

    def test_simple_xslt(self):
        case = simple_xslt_case
        actor = _TestActorWrapper(XSLT("xslt", xslt=case['xslt']))
        _input = XMLEvent(data=case['input'])
        actor.input = _input
        output = actor.output
        self.assertEqual(output.data_string(), case['output'])

    def test_xslt_raised_error(self):
        case = xslt_raised_error_case
        actor = _TestActorWrapper(XSLT("xslt", xslt=case['xslt']))
        _input = XMLEvent(data=case['input'])
        actor.input = _input
        output = actor.error
        self.assertEqual(output.error.__class__, case['output'])

