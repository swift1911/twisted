#! /usr/bin/python

import types

from zope.interface import implements, providedBy, Interface
from zope.interface.interface import InterfaceClass
from twisted.python import components
registerAdapter = components.registerAdapter
from tokens import ISlicer
import schema, slicer

## class RemoteMetaInterface(components.MetaInterface):
##     def __init__(self, iname, bases, dct):
##         components.MetaInterface.__init__(self, iname, bases, dct)
##         # determine all remotely-callable methods
##         methods = [name for name in dct.keys()
##                    if ((type(dct[name]) == types.FunctionType and
##                         not name.startswith("_")) or
##                        schema.IConstraint.providedBy(dct[name]))]
##         self.methods = methods
##         # turn them into constraints
##         for name in methods:
##             m = dct[name]
##             if not schema.IConstraint.providedBy(m):
##                 s = schema.RemoteMethodSchema(method=m)
##                 #dct[name] = s  # this doesn't work, dct is copied
##                 setattr(self, name, s)

## class IRemoteInterface(Interface, object):
##     __remote_name__ = None
##     __metaclass__ = RemoteMetaInterface

# this doesn't work. I don't know how to make a proper metaclass which can
# walk through the attributes and turn all the method definitions into
# constraints (this may be fundamentally incompatible with what
# zope.interface does). When I cheat and make IRemoteInterface less magical
# (using a metaclass which knows about pb-specific stuff but not
# zope.interface.Interface -type stuff), that breaks the providedBy() call
# used in getRemoteInterfaces(), below.

class RemoteMetaInterface(type):
    def __init__(self, iname, bases, attrs):
        # determine all remotely-callable methods
        methods = [name for name in attrs.keys()
                   if ((type(attrs[name]) == types.FunctionType and
                        not name.startswith("_")) or
                       schema.IConstraint.providedBy(attrs[name]))]
        self.methods = methods
        # turn them into constraints
        for name in methods:
            m = attrs[name]
            if not schema.IConstraint.providedBy(m):
                s = schema.RemoteMethodSchema(method=m)
                #attrs[name] = s  # this doesn't work, attrs is copied
                setattr(self, name, s)
        return type.__init__(self, iname, bases, attrs)
#IRemoteInterface = RemoteInterfaceClass("IRemoteInterface",
#                                        __module__="flavors")
#IRemoteInterface.__remote_name__ = None

class IRemoteInterface(object):
    __remote_name__ = None
    __metaclass__ = RemoteMetaInterface

#IRemoteInterface = Interface

def getRemoteInterfaces(obj):
    """Get a list of all RemoteInterfaces supported by the object."""
    interfaces = providedBy(obj)
    # TODO: versioned Interfaces!
    ilist = []
    for i in interfaces:
        if issubclass(i, IRemoteInterface):
            if i not in ilist:
                ilist.append(i)
    def getname(i):
        return i.__remote_name__ or i.__name__
    ilist.sort(lambda x,y: cmp(getname(x), getname(y)))
    # TODO: really? both sides must match
    return ilist

def getRemoteInterfaceNames(obj):
    """Get the names of all RemoteInterfaces supported by the object."""
    return [i.__remote_name__ or i.__name__ for i in getRemoteInterfaces(obj)]

class ICopyable(Interface):
    """I represent an object which is passed-by-value across PB connections.
    """

    def getTypeToCopy(self):
        """Return a string which names the class. This string must match
        the one that gets registered at the receiving end."""
    def getStateToCopy(self):
        """Return a state dictionary (with plain-string keys) which will be
        serialized and sent to the remote end. This state object will be
        given to the receiving object's setCopyableState method."""

class Copyable(object):
    implements(ICopyable)

    def getTypeToCopy(self):
        return reflect.qual(self.__class__)
    def getStateToCopy(self):
        return self.__dict__

class CopyableSlicer(slicer.BaseSlicer):
    """I handle ICopyable objects (things which are copied by value)."""
    def slice(self, streamable, banana):
        yield 'copyable'
        yield self.obj.getTypeToCopy()
        state = self.obj.getStateToCopy()
        for k,v in state.iteritems():
            yield k
            yield v
    def describe(self):
        return "<%s>" % self.obj.getTypeToCopy()
registerAdapter(CopyableSlicer, ICopyable, ISlicer)


class Copyable2(slicer.BaseSlicer):
    # I am my own Slicer. This has more methods than you'd usually want in a
    # base class, but if you can't register an Adapter for a whole class
    # hierarchy then you may have to use it.
    def getTypeToCopy(self):
        return reflect.qual(self.__class__)
    def getStateToCopy(self):
        return self.__dict__
    def slice(self, streamable, banana):
        yield 'instance'
        yield self.getTypeToCopy()
        yield self.getStateToCopy()
    def describe(self):
        return "<%s>" % self.getTypeToCopy()

#registerRemoteCopy(typename, factory)
#registerUnslicer(typename, factory)

class IRemoteCopy(Interface):
    """This interface defines what a RemoteCopy class must do. RemoteCopy
    subclasses are used as factories to create objects that correspond to
    Copyables sent over the wire.

    Note that the constructor of an IRemoteCopy class will be called without
    any arguments.
    
    """

    def setCopyableState(self, statedict):
        """I accept an attribute dictionary name/value pairs and use it to
        set my internal state.

        Some of the values may be Deferreds, which are placeholders for the
        as-yet-unreferenceable object which will eventually go there. If you
        receive a Deferred, you are responsible for adding a callback to
        update the attribute when it fires. [note:
        RemoteCopyUnslicer.receiveChild currently has a restriction which
        prevents this from happening, but that may go away in the future]

        Some of the objects referenced by the attribute values may have
        Deferreds in them (e.g. containers which reference recursive
        tuples). Therefore you must be careful about how much state
        inspection you perform within this method."""
        
    def getStateSchema(self):
        """I return an AttributeDictConstraint object which places
        restrictions on incoming attribute values. These restrictions are
        enforced as the tokens are received, before the state is passed to
        setCopyableState."""

class RemoteCopy(object):
    implements(IRemoteCopy)

    stateSchema = None
    def __init__(self):
        # the constructor will not be called with any args
        pass

    def setCopyableState(self, state):
        self.__dict__ = state
    def getStateSchema(self):
        return self.stateSchema

class RemoteCopyUnslicer(slicer.BaseUnslicer):
    attrname = None
    attrConstraint = None

    def __init__(self, factory):
        self.factory = factory
        self.schema = factory.stateSchema

    def start(self, count):
        self.d = {}
        self.count = count
        self.gettingAttrname = True
        self.deferred = Deferred()
        self.protocol.setObject(count, self.deferred)

    def checkToken(self, typebyte, size):
        if self.attrname == None:
            if typebyte not in (tokens.STRING, tokens.VOCAB):
                raise BananaError("RemoteCopyUnslicer keys must be STRINGs",
                                  self.where())

    def doOpen(self, opentype):
        if self.attrConstraint:
            self.attrConstraint.checkOpentype(opentype)
        unslicer = self.open(opentype)
        if unslicer:
            if self.attrConstraint:
                unslicer.setConstraint(self.attrConstraint)
        return unslicer

    def receiveChild(self, obj):
        self.propagateUnbananaFailures(obj)
        if self.attrname == None:
            attrname = obj
            s = self.schema
            if s:
                accept, self.attrConstraint = s.getAttrConstraint(attrname)
                assert accept
            self.attrname = attrname
        else:
            if isinstance(obj, Deferred):
                # TODO: this is an artificial restriction, and it might
                # be possible to remove it, but I need to think through
                # it carefully first
                raise BananaError("unreferenceable object in attribute",
                                  self.where())
            if self.d.has_key(self.attrname):
                raise BananaError("duplicate attribute name '%s'" % name,
                                  self.where())
            self.setAttribute(self.attrname, obj)
        self.gettingAttrname = not self.gettingAttrname

    def setAttribute(self, name, value):
        self.d[name] = value

    def receiveClose(self):
        # TODO: TASTE HERE IF YOU WANT TO LIVE!
        inst = Dummy()
        #inst.__classname__ = self.classname
        setInstanceState(inst, self.d)
        self.protocol.setObject(self.count, inst)
        self.deferred.callback(inst)
        return inst

    def describeSelf(self):
        if self.classname == None:
            return "<??>"
        me = "<%s>" % self.classname
        if self.gettingAttrname:
            return "%s.attrname??" % me
        else:
            return "%s.%s" % (me, self.attrname)
    

CopyableRegistry = {}
def registerRemoteCopy(typename, factory):
    # to be more clever than this, register an Unslicer instead
    assert issubclass(factory, RemoteCopy)
    CopyableRegistry[typename] = factory


class Referenceable(object):
    refschema = None
    # TODO: this wants to be in an adapter, not a base class
    def getSchema(self):
        # create and return a RemoteReferenceSchema for us
        if not self.refschema:
            interfaces = dict([
                (iface.__remote_name__ or iface.__name__, iface)
                for iface in getRemoteInterfaces(self)])
            self.refschema = schema.RemoteReferenceSchema(interfaces)
        return self.refschema

class ReferenceableSlicer(slicer.BaseSlicer):
    """I handle pb.Referenceable objects (things with remotely invokable
    methods, which are copied by reference).
    """
    opentype = ('remote',)

    def sliceBody(self, streamable, banana):
        puid = self.obj.processUniqueID()
        firstTime = self.broker.luids.has_key(puid)
        luid = self.broker.registerReference(self.obj)
        yield luid
        if not firstTime:
            # this is the first time the Referenceable has crossed this
            # wire. In addition to the luid, send the interface list to the
            # far end.
            yield getRemoteInterfaceNames(self.obj)
            # TODO: maybe create the RemoteReferenceSchema now
            # obj.getSchema()
registerAdapter(ReferenceableSlicer, Referenceable, ISlicer)