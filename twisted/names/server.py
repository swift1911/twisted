
# Twisted, the Framework of Your Internet
# Copyright (C) 2001 Matthew W. Lefkowitz
# 
# This library is free software; you can redistribute it and/or
# modify it under the terms of version 2.1 of the GNU Lesser General Public
# License as published by the Free Software Foundation.
# 
# This library is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
# 
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA

"""
Async DNS server

API Stability: Unstable

Future plans: Have this work.  Better config file format maybe;
  Make sure to differentiate between different classes; handle
  recursive lookups; notice truncation bit; probably other stuff.

@author: U{Jp Calderone <exarkun@twistedmatrix.com>}
"""

from __future__ import nested_scopes

# System imports
import struct

# Twisted imports
from twisted.internet import protocol
from twisted.protocols import dns

class Authority:
    """
    Guess.
    """

    def __init__(self, filename):
        g, l = self.setupConfigNamespace(), {}
        execfile(filename, g, l)
        if not l.has_key('zone'):
            raise ValueError, "No zone defined in " + filename
        
        self.records = {}
        for rr in l['zone']:
            if isinstance(rr[1], dns.Record_SOA):
                self.soa = rr
            self.records.setdefault(rr[0], []).append(rr[1])


    def wrapRecord(self, type):
        return lambda name, *arg, **kw: (name, type(*arg, **kw))


    def setupConfigNamespace(self):
        r = {}
        for record in [x for x in dir(dns) if x.startswith('Record_')]:
            type = getattr(dns, record)
            f = self.wrapRecord(type)
            r[record[len('Record_'):]] = f
        return r


class DNSServerFactory(protocol.ServerFactory):
    def __init__(self, authorities):
        self.authorities = authorities


    def buildProtocol(self, addr):
        p = dns.TCPDNSClientProtocol(self)
        p.factory = self
        return p


    def connectionMade(self, protocol):
        pass


    def handleQuery(self, message, protocol, address):
        answers = []
        for q in message.queries:
            for a in self.authorities:
                if a.records.has_key(str(q.name).lower()):
                    for r in a.records[str(q.name).lower()]:
                        if q.type == r.TYPE or q.type == dns.ALL_RECORDS:
                            answers.append(dns.RRHeader(str(q.name), r.TYPE, q.cls, 10))
                            answers[-1].payload = r
        if len(answers):
            message.answers = answers
            message.auth = 1
        else:
            message.answers = []
            message.rCode = dns.ENAME
        try:
            protocol.writeMessage(message)
        except TypeError:
            protocol.writeMessage(message, address)


    def handleInverseQuery(self, message, protocol, address):
        message.rCode = dns.ENOTIMP
        try:
            protocol.writeMessage(message)
        except TypeError:
            protocol.writeMessage(message, address)


    def handleStatus(self, message, protocol, address):
        message.rCode = dns.ENOTIMP
        try:
            protocol.writeMessage(message)
        except TypeError:
            protocol.writeMessage(message, address)
        

    def handleOther(self, message, protocol, address):
        message.rCode = dns.ENOTIMP
        try:
            protocol.writeMessage(message)
        except TypeError:
            protocol.writeMessage(message, address)


    def messageReceived(self, message, protocol, address = None):
        message.recAv = 0
        message.answer = 1
        
        if message.opCode == dns.OP_QUERY:
            self.handleQuery(message, protocol, address)
        elif message.opCode == dns.OP_INVERSE:
            self.handleInverseQuery(message, protocol, address)
        elif message.opCode == dns.OP_STATUS:
            self.handleStatus(message, protocol, address)
        else:
            self.handleOther(message, protocol, address)
