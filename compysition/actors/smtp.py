#!/usr/bin/env python
#
# -*- coding: utf-8 -*-
#
# Created by Adam Fiebig
# Last modified: 4-15-2015 by Adam Fiebig

import smtplib

import email
import traceback
import re

from email.mime.text import MIMEText
#from bs4 import BeautifulSoup

from compysition.actor import Actor
from compysition.event import XMLEvent, JSONEvent

class SMTPOut(Actor):

    input = XMLEvent
    output = XMLEvent

    '''**Module which sends mime emails with propertied specified in XML event data.**

    Parameters:

        - name (str):       The instance name.
    '''

    address_regex = re.compile("^.*@.*$")

    def __init__(self, name, from_address=None, domain=None, key=None, host=("localhost", 25), *args, **kwargs):
        Actor.__init__(self, name, *args, **kwargs)
        self.blockdiag_config["shape"] = "mail"
        self.logger.info("Initialized SMTPOut Actor")
        self.key = key or self.name
        self.host = host
        self.domain = domain
        self.address = self.normalize_address(from_address, self.domain)
        self.body_tag = 'Body'

    def normalize_address(self, address, domain):
        """
        If an address does not match some_address@some_domain.com, concatenate the address and domain.
        If the address is none, it will return none.
        If the address is not a full address the domain is none, it will return none
        """
        if address is not None and not self.address_regex.match(address):
            if domain is not None:
                address = "{address}@{domain}".format(address=address, domain=domain)
            else:
                address = None

        return address

    def consume(self, event, *args, **kwargs):
        msg_xml = event.data
        to = msg_xml.find("To").text
        from_element = msg_xml.find("From")
        from_address = self.normalize_address(from_element.text, self.domain)
        from_element.text = from_address
        if to != "None" and to is not None:
            msg = MIMEText(msg_xml.find(self.body_tag).text)    # Create a mime obj with our body text
            for element in msg_xml:                             # Set each tag's text as a property on the MIMEText obj
                if element.tag != self.body_tag:
                    msg[element.tag] = element.text

            try:
                self.send(msg, to, from_address)
            except Exception as err:
                self.logger.error("Error sending message: {err}".format(err=traceback.format_exc()), event=event)
            else:
                self.logger.info("Email sent to {to} from {from_address} via smtp server {host}".format(to=to,
                                                                                                        from_address=from_address,
                                                                                                        host=self.host), event=event)
        else:
            self.logger.info("No email recipient specified, notification was not sent", event=event)

        self.send_event(event)

    def send(self, msg, to, from_address):
        sender = smtplib.SMTP(self.host)
        sender.sendmail(from_address, to.split(","), msg.as_string())
        sender.quit()

"""
# NOT FUNCTIONING
class SMTPIn(Actor):
    '''**Module which sends mime emails with propertied specified in XML event data.**

    Parameters:

        - name (str):       The instance name.
    '''

    output = [XMLEvent, JSONEvent]

    def __init__(self, name, host="localhost", ports=[25], output_format='xml', keyfile=None, certfile=None, ssl_version=None, *args, **kwargs):
        Actor.__init__(self, name, *args, **kwargs)
        self.blockdiag_config["shape"] = "mail"
        self.output_format = output_format
        if not isinstance(ports, list):
            ports = [ports]

        self.servers = []
        for port in ports:
            server = gsmtpd_server.SMTPServer("{host}:{port}".format(host=host, port=port),
                                               keyfile=keyfile,
                                               certfile=certfile,
                                               ssl_version=ssl_version)
            server.process_message = self.process_message
            self.servers.append(server)

    def pre_hook(self):
        [server.start() for server in self.servers]

    def process_message(self, peer, mailfrom, rcpttos, data):
        headers = email.message_from_string(data)
        payload = headers.get_payload()
        new_data = dict(**headers)

        payload_data = headers.get_payload()
        if isinstance(payload_data, list):
            payload = filter(lambda x: x.get_content_type() == "text/plain", payload)[0]

            if payload is None:
                html = filter(lambda x: x.get_content_type() == "text/html", payload)[0]
                payload = BeautifulSoup(html.get_payload(), "lxml").get_text()
            else:
                payload = payload.get_payload()

            payload_data = payload

        new_data['payload'] = payload_data

        if self.output_format == 'xml':
            new_data['email'] = new_data
            event = XML(data=new_data)
        else:
            event = JSON(data=new_data)

        self.send_event(event)

    def consume(self, event, *args, **kwargs):
        pass
"""