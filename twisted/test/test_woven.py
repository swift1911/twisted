# Twisted, the Framework of Your Internet
# Copyright (C) 2001-2002 Matthew W. Lefkowitz
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

from pyunit import unittest
from twisted.web import server, resource, microdom, domhelpers
from twisted.protocols import http
from twisted.test import test_web
from twisted.internet import reactor, defer

from twisted.web.woven import template, model, view, controller, widgets, input, page, guard

outputNum = 0

# Reusable test harness

class WovenTC(unittest.TestCase):
    modelFactory = lambda self: None
    resourceFactory = None
    def setUp(self):
        self.m = self.modelFactory()
        self.t = self.resourceFactory(self.m)
        self.r = test_web.DummyRequest([])
        self.prerender()
        self.t.render(self.r, block=1)
        
        self.channel = "a fake channel"
        self.output = ''.join(self.r.written)
        assert self.output, "No output was generated by the test."
        global outputNum
        open("wovenTestOutput%s.html" % (outputNum + 1), 'w').write(self.output)
        outputNum += 1
        self.d = microdom.parseString(self.output)
    
    def prerender(self):
        pass

# Test 1
# Test that replacing nodes with a string works properly


class SimpleTemplate(template.DOMTemplate):
    template = """<http>
    <head>
        <title id="title"><span view="getTitle">Hello</span></title>
    </head>
    <body>
        <h3 id="hello"><span view="getHello">Hi</span></h3>
    </body>
</http>"""
    
    def factory_getTitle(self, request, node):
        return "Title"
    
    def factory_getHello(self, request, node):
        return "Hello"

class DOMHelpersTest(unittest.TestCase):
    def testMicrodom(self):
        d = microdom.parseString("<x id='hello' />")
        helloNode = d.getElementById("hello")
        self.failUnlessEqual(helloNode, d.documentElement)

    def testDoctype(self):
        d = microdom.parseString('''<?xml version="1.0"?>
<!DOCTYPE html PUBLIC "-//W3C//DTD XHTML 1.0 Transitional//EN" "http://www.w3.org/TR/xhtml1/DTD/xhtml1-transitional.dtd">
<dummy/>
''')
        d2 = microdom.parseString(d.toxml())
        assert d.doctype, "Doctype not set!"
        assert d.doctype == d2.doctype, "Doctypes not equal"


class DOMTemplateTest(WovenTC):
    resourceFactory = SimpleTemplate
    def testSimpleRender(self):
        titleNode = self.d.getElementById("title")
        helloNode = self.d.getElementById("hello")
        
        assert domhelpers.gatherTextNodes(titleNode) == 'Title'
        assert domhelpers.gatherTextNodes(helloNode) == 'Hello'


# Test 2
# Test just like the first, but with Text widgets

class TemplateWithWidgets(SimpleTemplate):
    def factory_getTitle(self, request, node):
        return widgets.Text("Title")

    def factory_getHello(self, request, node):
        return widgets.Text("Hello")


class TWWTest(DOMTemplateTest):
    resourceFactory = TemplateWithWidgets


# Test 3
# Test a fancier widget, and controllers handling submitted input


class MDemo(model.Model):
    foo = "Hello world"
    color = 'blue'


class FancyBox(widgets.Widget):
    def setUp(self, request, node, data):
        self['style'] = 'margin: 1em; padding: 1em; background-color: %s' % data


class VDemo(view.View):
    template = """<html>

<div id="box" model="color" view="FancyBox"></div>

<form action="">
Type a color and hit submit:
<input type="text" controller="change" model="color" name="color" />
<input type="submit" />
</form>

</html>
"""
    def wvfactory_FancyBox(self, request, node, model):
        return FancyBox(model)
    
    def renderFailure(self, failure, request):
        return failure


class ChangeColor(input.Anything):
    def commit(self, request, node, data):
        session = request.getSession()
        session.color = data
        self.model.setData(data)
        self.model.notify({'request': request})


class CDemo(controller.Controller):
    def setUp(self, request):
        session = request.getSession()
        self.model.color = getattr(session, 'color', self.model.color)

    def factory_change(self, request, node, model):
        return ChangeColor(model)


view.registerViewForModel(VDemo, MDemo)
controller.registerControllerForModel(CDemo, MDemo)


class ControllerTest(WovenTC):
    modelFactory = MDemo
    resourceFactory = CDemo
    
    def prerender(self):
        self.r.addArg('color', 'red')
    
    def testControllerOutput(self):
        boxNode = self.d.getElementById("box")
        assert boxNode, "Test %s failed" % outputNum
        style = boxNode.getAttribute("style")
        styles = style.split(";")
        sDict = {}
        for item in styles:
            key, value = item.split(":")
            key = key.strip()
            value = value.strip()
            sDict[key] = value
        
#         print sDict
        assert sDict['background-color'] == 'red'


# Test 4
# Test a list, a list widget, and Deferred data handling

identityList = ['asdf', 'foo', 'fredf', 'bob']

class MIdentityList(model.Model):
    def __init__(self):
        model.Model.__init__(self)
        self.identityList = defer.Deferred()
        self.identityList.callback(identityList)


class VIdentityList(view.View):
    template = """<html>
    <ul id="list" view="identityList" model="identityList">
        <li listItemOf="identityList" view="text">
            Stuff.
        </li>
    </ul>
</html>"""

    def wvfactory_identityList(self, request, node, model):
        return widgets.List(model)

    def wvfactory_text(self, request, node, model):
        return widgets.Text(model)

    def renderFailure(self, failure, request):
        return failure


class CIdentityList(controller.Controller):
    pass


view.registerViewForModel(VIdentityList, MIdentityList)
controller.registerControllerForModel(CIdentityList, MIdentityList)


class ListDeferredTest(WovenTC):
    modelFactory = MIdentityList
    resourceFactory = CIdentityList

    def testOutput(self):
        listNode = self.d.getElementById("list")
        assert listNode, "Test %s failed; there was no element with the id 'list' in the output" % outputNum
        liNodes = domhelpers.getElementsByTagName(listNode, 'li')
        assert len(liNodes) == len(identityList), "Test %s failed; the number of 'li' nodes did not match the list size" % outputNum


# Test 5
# Test nested lists

class LLModel(model.Model):
    data = [['foo', 'bar', 'baz'],
            ['gum', 'shoe'],
            ['ggg', 'hhh', 'iii']
           ]


class LLView(view.View):
    template = """<html>
    <ul id="first" view="List" model="data">
        <li pattern="listItem" view="DefaultWidget">
            <ol view="List">
                <li pattern="listItem" view="Text" />
            </ol>
        </li>
    </ul>
</html>"""

    def wvfactory_List(self, request, node, model):
        return widgets.List(model)


class NestedListTest(WovenTC):
    modelFactory = LLModel
    resourceFactory = LLView
    
    def testOutput(self):
        listNode = self.d.getElementById("first")
        assert listNode, "Test %s failed" % outputNum
        liNodes = filter(lambda x: hasattr(x, 'tagName') and x.tagName == 'li', listNode.childNodes)
#        print len(liNodes), len(self.m.data), liNodes, self.m.data
        assert len(liNodes) == len(self.m.data), "Test %s failed" % outputNum
        for i in range(len(liNodes)):
            sublistNode = domhelpers.getElementsByTagName(liNodes[i], 'ol')[0]
            subLiNodes = domhelpers.getElementsByTagName(sublistNode, 'li')
            assert len(self.m.data[i]) == len(subLiNodes)

# Test 6
# Test notification when a model is a dict or a list

class MNotifyTest(model.Model):
    def initialize(self, *args, **kwargs):
        self.root = {"inventory": [], 'log': ""}


class VNotifyTest(view.View):
    template = """<html>
    <body>
        <ol id="theList" model="root/inventory" view="List">
            <li view="someText" pattern="listItem" />
        </ol>
        
        <form action="">
            <input model="root" view="DefaultWidget" controller="updateInventory" name="root" />
            <input type="submit" />
        </form>
    </body>
</html>"""

    def wvfactory_someText(self, request, node, m):
        return widgets.Text(m)

class InventoryUpdater(input.Anything):    
    def commit(self, request, node, data):
        invmodel = self.model.getSubmodel("inventory")
        log = self.model.getSubmodel("log")
        inv = invmodel.getData()
        inv.append(data) # just add a string to the list
        log.setData(log.getData() + ("%s added to servers\n" % data))
        invmodel.setData(inv)
        invmodel.notify({'request': request})


class CNotifyTest(controller.Controller):
    def wcfactory_updateInventory(self, request, node, model):
        return InventoryUpdater(model)


view.registerViewForModel(VNotifyTest, MNotifyTest)
controller.registerControllerForModel(CNotifyTest, MNotifyTest)

class NotifyTest(WovenTC):
    modelFactory = MNotifyTest
    resourceFactory = CNotifyTest

    def prerender(self):
        self.r.addArg('root', 'test')

    def testComplexNotification(self):
        listNode = self.d.getElementById("theList")
        assert listNode, "Test %s failed" % outputNum
        liNodes = domhelpers.getElementsByTagName(listNode, 'li')
        assert liNodes, "DOM was not updated by notifying Widgets. Test %s" % outputNum
        text = domhelpers.gatherTextNodes(liNodes[0])
        assert text == "test", "Wrong output: %s. Test %s" % (text, outputNum)

view.registerViewForModel(LLView, LLModel)

#### Test 7
# Test model path syntax
# model="/" should get you the root object
# model="." should get you the current object
# model=".." should get you the parent model object


# xxx sanity check for now; just make sure it doesn't raise anything

class ModelPathTest(WovenTC):
    modelFactory = lambda self: ['hello', ['hi', 'there'], 
                        'hi', ['asdf', ['qwer', 'asdf']]]
    resourceFactory = page.Page

    def prerender(self):
        self.t.template = """<html>
    <div model="0" view="None">
        <div model=".." view="Text" />
    </div>
    
    <div model="0" view="None">
        <div model="../1/../2/../3" view="Text" />
    </div>

    <div model="0" view="None">
        <div model="../3/1/./1" view="Text" />
    </div>
    
    <div model="3/1/0" view="None">
        <div model="/" view="Text" />
    </div>

    <div model="3/1/0" view="None">
        <div model="/3" view="Text" />
    </div>

</html>"""

class FakeHTTPChannel:
    # TODO: this should be an interface in twisted.protocols.http... lots of
    # things want to fake out HTTP
    def __init__(self):
        self.transport = self
        self.factory = self

    # 'factory' attribute needs this
    def log(self, req):
        pass

    # 'channel' of request needs this
    def requestDone(self, req):
        self.req = req

    # 'transport' attribute needs this
    def getPeer(self):
        return "fake", "fake", "fake"
    def getHost(self):
        return "fake", "fake", 80

    def write(self, data):
        # print data
        pass
    def writeSequence(self, datas):
        for data in datas:
            self.write(data)

class FakeHTTPRequest(server.Request):
    def __init__(self, *args, **kw):
        server.Request.__init__(self, *args, **kw)
        self._cookieCache = {}
        from cStringIO import StringIO
        self.content = StringIO()
        self.received_headers['host'] = 'fake.com'
        
    def addCookie(self, k, v, *args,**kw):
        server.Request.addCookie(self,k,v,*args,**kw)
        assert not self._cookieCache.has_key(k), "Should not be setting duplicate cookies!"
        self._cookieCache[k] = v
        self.received_cookies[k] = v

    def processingFailed(self, fail):
        raise fail

class FakeSite(server.Site):
    def getResourceFor(self, req):
        res = server.Site.getResourceFor(self,req)
        self.caughtRes = res
        return res

from twisted.web import static

class GuardTest(unittest.TestCase):
    def testSessionInit(self):
        sessWrapped = static.Data("you should never see this", "text/plain")
        swChild = static.Data("YES", "text/plain")
        sessWrapped.putChild("yyy",swChild)
        sess = guard.SessionWrapper(sessWrapped)
        da = static.Data("b","text/plain")
        da.putChild("xxx", sess)
        st = FakeSite(da)
        chan = FakeHTTPChannel()
        chan.site = st

        # first we're going to make sure that the session doesn't get set by
        # accident when browsing without first explicitly initializing the
        # session
        req = FakeHTTPRequest(chan, queued=0)
        req.requestReceived("GET", "/xxx/yyy", "1.0")
        assert len(req._cookieCache.values()) == 0, req._cookieCache.values()
        self.assertEquals(req.getSession(),None)

        # now we're going to make sure that the redirect and cookie are properly set
        req = FakeHTTPRequest(chan, queued=0)
        req.requestReceived("GET", "/xxx/"+guard.INIT_SESSION, "1.0")
        ccv = req._cookieCache.values()
        self.assertEquals(len(ccv),1)
        cookie = ccv[0]
        # redirect set?
        self.failUnless(req.headers.has_key('location'))
        # redirect matches cookie?
        self.assertEquals(req.headers['location'].split('/')[-1], cookie)
        # URL is correct?
        self.assertEquals(req.headers['location'],
                          'http://fake.com/xxx/'+cookie)
        oldreq = req
        
        # now let's try with a request for the session-cookie URL that has a cookie set
        req = FakeHTTPRequest(chan, queued=0)
        req.received_cookies[sess.cookieKey] = cookie
        url = "/"+(oldreq.headers['location'].split('http://fake.com/',1))[1]
        req.requestReceived("GET",url, "1.0")
        self.assertEquals(req.headers['location'],
                          'http://fake.com/xxx/')
        
