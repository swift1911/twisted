# -*- test-case-name: twisted.test.test_rootresolve -*-
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
Resolver implementation for querying successive authoritative servers to
lookup a record, starting from the root nameservers.

API Stability: Unstable

@author U{Jp Calderone<mailto:exarkun@twistedmatrix.com>}

todo: robustify it
      break discoverAuthority into several smaller functions
      documentation
"""

from __future__ import generators

import random

from twisted.flow import flow
from twisted.python import log
from twisted.internet import defer
from twisted.protocols import dns
from twisted.names import common

def retry(t, p, *args):
    t = list(t)
    def errback(failure):
        failure.trap(defer.TimeoutError)
        if not t:
            return failure
        return p.query(timeout=t.pop(0), *args
            ).addErrback(errback
            )
    return p.query(timeout=t.pop(0), *args
        ).addErrback(errback
        )

class _DummyController:
    def messageReceived(self, *args):
        pass

class Resolver(common.ResolverBase):
    def __init__(self, hints):
        common.ResolverBase.__init__(self)
        self.hints = hints

    def _lookup(self, name, cls, type, timeout):
        return flow.Deferred(discoverAuthority(name, self.hints)
            ).addCallback(lambda a: a[0]
            ).addCallback(self.discoveredAuthority, name, cls, type, timeout
            )
        return d
    
    def discoveredAuthority(self, auth, name, cls, type, timeout):
        from twisted.names import client
        q = dns.Query(name, cls, type)
        r = client.Resolver(servers=[(auth, dns.PORT)])
        d = r.queryUDP([q], timeout)
        d.addCallback(r.filterAnswers)
        return d

def lookupNameservers(host, atServer, p=None):
    if p is None:
        p = dns.DNSDatagramProtocol(_DummyController())
        p.noisy = False
    return retry(
        (1, 3, 11, 45),                     # Timeouts
        p,                                  # Protocol instance
        (atServer, dns.PORT),               # Server to query
        [dns.Query(host, dns.NS, dns.IN)]   # Question to ask
    )

def lookupAddress(host, atServer, p=None):
    if p is None:
        p = dns.DNSDatagramProtocol(_DummyController())
        p.noisy = False
    return retry(
        (1, 3, 11, 45),                     # Timeouts
        p,                                  # Protocol instance
        (atServer, dns.PORT),               # Server to query
        [dns.Query(host, dns.A, dns.IN)]    # Question to ask
    )

def discoverAuthority(host, roots, cache=None, p=None):
    if cache is None:
        cache = {}

    rootAuths = list(roots)

    parts = host.rstrip('.').split('.')
    parts.reverse()
    
    authority = rootAuths.pop()
    
    soFar = ''
    for part in parts:
        soFar = part + '.' + soFar
        
        msg = flow.wrap(lookupNameservers(soFar, authority, p))
        yield msg
        msg = msg.next()

        records = msg.answers + msg.authority + msg.additional
        nameservers = [r for r in records if r.type == dns.NS]
        
        # print 'Records for', soFar, ':', records
        # print 'NS for', soFar, ':', nameservers

        if not records:
            raise IOError("No records")
        
        for r in records:
            if r.type == dns.A:
                cache[str(r.name)] = r.payload.dottedQuad()

        newAuth = None
        for r in records:
            if r.type == dns.NS:
                if str(r.payload.name) in cache:
                    newAuth = cache[str(r.payload.name)]
                    break
        else:
            for addr in records:
                if addr.type == dns.A and addr.name == r.name:
                    newAuth = addr.payload.dottedQuad()
                    break
        if newAuth is not None:
            authority = newAuth
        else:
            if nameservers:
                r = str(nameservers[0].payload.name)
                # print 'Recursively discovering authority for', r
                authority = flow.wrap(discoverAuthority(r, roots, cache, p))
                yield authority
                authority = authority.next()
                # print 'Discovered to be', authority, 'for', r
            else:
                # print 'Doing address lookup for', soFar, 'at', authority
                msg = flow.wrap(lookupAddress(soFar, authority, p))
                yield msg
                msg = msg.next()
                records = msg.answers + msg.authority + msg.additional
                addresses = [r for r in records if r.type == dns.A]
                if addresses:
                    authority = addresses[0].payload.dottedQuad()
                else:
                    raise IOError("Resolution error")
    yield authority

def makePlaceholder(deferred, name):
    def placeholder(*args, **kw):
        deferred.addCallback(lambda r: getattr(r, name)(*args, **kw))
        return deferred
    return placeholder

class DeferredResolver:
    def __init__(self, resolverDeferred):
        resolverDeferred.addCallback(self.gotRealResolver)
        self.waiting = []

    def gotRealResolver(self, resolver):
        w = self.waiting
        self.__dict__ = resolver.__dict__
        self.__class__ = resolver.__class__
        for d in w:
            d.callback(resolver)

    def __getattr__(self, name):
        if name.startswith('lookup') or name in ('getHostByName', 'query'):
            self.waiting.append(defer.Deferred())
            return makePlaceholder(self.waiting[-1], name)
        raise AttributeError(name)

def bootstrap(resolver):
    """Lookup the root nameserver addresses using the given resolver
    
    Return a Resolver which will eventually become a C{root.Resolver}
    instance that has references to all the root servers that we were able
    to look up.
    """
    domains = [chr(ord('a') + i) for i in range(13)]
    from twisted.python import log
    # f = lambda r: (log.msg('Root server address: ' + str(r)), r)[1]
    f = lambda r: r
    L = [resolver.getHostByName('%s.root-servers.net' % d).addCallback(f) for d in domains]
    d = defer.DeferredList(L)
    d.addCallback(lambda r: Resolver([e[1] for e in r if e[0]]))
    return DeferredResolver(d)

if __name__ == '__main__':
    from twisted.python import log
    import sys
    if len(sys.argv) < 2:
        print 'Specify a domain'
    else:
        log.startLogging(sys.stdout)
        from twisted.names.client import ThreadedResolver
        r = bootstrap(ThreadedResolver())
        d = r.lookupAddress(sys.argv[1])
        d.addCallbacks(log.msg, log.err).addBoth(lambda _: reactor.stop())
        from twisted.internet import reactor
        reactor.run()
