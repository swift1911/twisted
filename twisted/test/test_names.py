
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
Test cases for twisted.names.
"""
import sys
from pyunit import unittest

from twisted.internet import reactor, protocol, defer
from twisted.names import client, server, common
from twisted.protocols import dns
from twisted.python import log


gotResponse = 0
PORT = 2053

def setDone(message):
    global gotResponse
    gotResponse = 1
    return message

def getPayload(message):
    global gotResponse
    gotResponse = 1
    return [answer.payload for answer in message.answers]


class NoFileAuthority(common.ResolverBase):
    def __init__(self, soa, records):
        common.ResolverBase.__init__(self)
        self.soa, self.records = soa, records

    def _lookup(self, name, cls, type, timeout = 10):
        if name.lower().endswith(self.soa[0].lower()):
            l = [r for r in self.records[name.lower()] if type == dns.ALL_RECORDS or r.TYPE == type]
            for r in l:
                r.ttl = 10
            print 'results are', l
            return defer.succeed(l)
        return defer.fail(dns.DomainError(name))


soa_record = dns.Record_SOA(
                    mname = 'test-domain.com',
                    rname = 'root.test-domain.com',
                    serial = 100,
                    refresh = 1234,
                    minimum = 7654,
                    expire = 19283784,
                    retry = 15
                )

reverse_soa = dns.Record_SOA(
                     mname = '93.84.28.in-addr.arpa',
                     rname = '93.84.28.in-addr.arpa',
                     serial = 120,
                     refresh = 54321,
                     minimum = 382,
                     expire = 11193983,
                     retry = 30
                )

class ServerDNSTestCase(unittest.DeferredTestCase):
    """Test cases for DNS server and client."""
    
    def setUp(self):
        self.factory = server.DNSServerFactory([
            NoFileAuthority(
                soa = ('test-domain.com', soa_record),
                records = {
                    'test-domain.com': [
                        dns.Record_A('127.0.0.1'),
                        dns.Record_NS('39.28.189.39'),
                        dns.Record_MX(10, 'host.test-domain.com'),
                        dns.Record_HINFO(os='Linux', cpu='A Fast One, Dontcha know'),
                        soa_record
                    ],
                    'host.test-domain.com': [
                        dns.Record_A('123.242.1.5'),
                        dns.Record_A('0.255.0.255'),
                    ],
                    'host-two.test-domain.com': [
#
#  Python bug
#                        dns.Record_A('255.255.255.255'),
#
                        dns.Record_A('255.255.255.254'),
                        dns.Record_A('0.0.0.0')
                    ],
                }
            ), NoFileAuthority(
                soa = ('93.84.28.in-addr.arpa', reverse_soa),
                records = {
                    '123.93.84.28.in-addr.arpa': [
                        dns.Record_PTR('test.host-reverse.lookup.com'),
                        reverse_soa
                    ]
                }
            )
        ], verbose=2)
        
        self.listenerTCP = reactor.listenTCP(PORT, self.factory)
        
        p = dns.DNSDatagramProtocol(self.factory)
        self.listenerUDP = reactor.listenUDP(PORT, p)
        
        self.resolver = client.Resolver(servers=[('127.0.0.1', PORT)])


    def tearDown(self):
        self.listenerTCP.stopListening()
        self.listenerUDP.stopListening()


    def testAddressRecord1(self):
        """Test DNS 'A' record queries"""
        global gotResponse
        gotResponse = 0
        r = self.resolver
        self.deferredFailUnlessEqual(
            r.lookupAddress('test-domain.com').addBoth(setDone),
            [dns.Record_A('127.0.0.1')]
        )
        while not gotResponse:
            reactor.iterate(0.05)


    def testAddressRecord2(self):
        """Test DNS 'A' record queries"""
        global gotResponse
        gotResponse = 0
        r = self.resolver
        self.deferredFailUnlessEqual(
            r.lookupAddress('host.test-domain.com').addBoth(setDone),
            [dns.Record_A('123.242.1.5'), dns.Record_A('0.255.0.255')]
        )
        while not gotResponse:
            reactor.iterate(0.05)


    def testAdressRecord3(self):
        """Test DNS 'A' record queries"""
        global gotResponse
        gotResponse = 0
        r = self.resolver
        self.deferredFailUnlessEqual(
            r.lookupAddress('host-two.test-domain.com').addBoth(setDone),
            [dns.Record_A('255.255.255.254'), dns.Record_A('0.0.0.0')]
        )
        while not gotResponse:
            reactor.iterate(0.05)


    def testAuthority(self):
        """Test DNS 'SOA' record queries"""
        global gotResponse
        gotResponse = 0
        r = self.resolver
        self.deferredFailUnlessEqual(
            r.lookupAuthority('test-domain.com').addBoth(setDone),
            [soa_record]
        )
        while not gotResponse:
            reactor.iterate(0.05)


    def testMailExchangeRecord(self):
        """Test DNS 'MX' record queries"""
        global gotResponse
        gotResponse = 0
        r = self.resolver
        self.deferredFailUnlessEqual(
            r.lookupMailExchange('test-domain.com').addBoth(setDone),
            [dns.Record_MX(10, 'host.test-domain.com')]
        )
        while not gotResponse:
            reactor.iterate(0.05)


    def testNameserver(self):
        """Test DNS 'NS' record queries"""
        global gotResponse
        gotResponse = 0
        r = self.resolver
        self.deferredFailUnlessEqual(
            r.lookupNameservers('test-domain.com').addBoth(setDone),
            [dns.Record_NS('39.28.189.39')]
        )
        while not gotResponse:
            reactor.iterate(0.05)


    def testHINFO(self):
        """Test DNS 'HINFO' record queries"""
        global gotResponse
        gotResponse = 0
        r = self.resolver
        self.deferredFailUnlessEqual(
            r.lookupHostInfo('test-domain.com').addBoth(setDone),
            [dns.Record_HINFO(os='Linux', cpu='A Fast One, Dontcha know')]
        )
        while not gotResponse:
            reactor.iterate(0.05)


    def testPTR(self):
        """Test DNS 'PTR' record queries"""
        global gotResponse
        gotResponse = 0
        r = self.resolver
        self.deferredFailUnlessEqual(
            r.lookupPointer('123.93.84.28.in-addr.arpa').addBoth(setDone),
            [dns.Record_PTR('test.host-reverse.lookup.com')]
        )
        while not gotResponse:
            reactor.iterate(0.05)
