
import random, string

from twisted.application import internet, service
from twisted.internet import protocol, task
from twisted.protocols import telnet
from twisted.python import log

import insults

class DrawingFinished(Exception):
    pass

class Drawable:
    n = 0

    def __init__(self, proto, line, col):
        self.proto = proto
        self.line = line
        self.col = col

    def drawLines(self, s):
        lines = s.splitlines()
        c = self.col - len(lines)
        for l in lines:
            self.proto.cursorPosition(c, self.line - len(lines) / 2)
            self.proto.write(l)
            c += 1

    def iterate(self):
        getattr(self, 'erase_' + str(self.n))()
        self.n += 1
        f = getattr(self, 'draw_' + str(self.n), None)
        if f is None:
            raise DrawingFinished()
        f()

    def erase_0(self):
        pass


class Splat(Drawable):
    def draw_1(self):
        # . .
        #. . .
        # . .
        self.drawLines(' . .\n. . .\n . .')

    def erase_1(self):
        self.drawLines('    \n     \n    ')

    def draw_2(self):
        #  . . . .
        # . o o o .
        #. o o o o .
        # . o o o .
        #  . . . .
        self.drawLines('  . . . .\n . o o o .\n. o o o o .\n . o o o .\n  . . . .')

    def erase_2(self):
        self.drawLines('         \n          \n           \n          \n         ')

    def draw_3(self):
        #  o o o o
        # o O O O o
        #o O O O O o
        # o O O O o
        #  o o o o
        self.drawLines('  o o o o\n o O O O o\no O O O O o\n o O O O o\n  o o o o')

    erase_3 = erase_2

    def draw_4(self):
        #  O O O O
        # O . . . O
        #O . . . . O
        # O . . . O
        #  O O O O
        self.drawLines('  O O O O\n O . . . O\nO . . . . O\n O . . . O\n  O O O O')

    erase_4 = erase_3

    def draw_5(self):
        #  . . . .
        # .       .
        #.         .
        # .       .
        #  . . . .
        self.drawLines('  . . . .\n .       .\n.         .\n .       .\n  . . . .')

    erase_5 = erase_4

class Drop(Drawable):
    def draw_1(self):
        # o
        self.drawLines(' o')

    def erase_1(self):
        self.drawLines('  ')

    def draw_2(self):
        # _
        #/ \
        #| |
        #\./
        self.drawLines(' _ \n/ \\\n\\./')

    def erase_2(self):
        self.drawLines('  \n   \n   ')

    def draw_3(self):
        # O
        self.drawLines(' O')

    def erase_3(self):
        self.drawLines('  ')

class DemoHandler(insults.TerminalListener):
    def run(self, proto):
        # Clear the screen, matey
        proto.eraseDisplay()

        self._call = task.LoopingCall(self._iterate, proto)
        self._call.start(0.2)

    def _iterate(self, proto):
        # Move to a random location on the screen
        line = random.randrange(60) + 20
        col = random.randrange(10) + 10

        s = random.choice((Splat, Drop))(proto, line, col)
        c = task.LoopingCall(s.iterate)
        c.start(0.05).addErrback(lambda f: f.trap(DrawingFinished)).addErrback(log.err)

    # ITerminalListener
    def unhandledControlSequence(self, seq):
        log.msg("Client sent something weird: %r" % (seq,))

    def keystrokeReceived(self, keyID):
        log.msg("Client sent: %r" % (keyID,))

class SillyProtocol(insults.ServerProtocol):
    def connectionMade(self):
        self.handler = DemoHandler()
        self.handler.run(self)

MODE = '\x01'
EDIT = 1
TRAPSIG = 2
MODE_ACK = 4
SOFT_TAB = 8
LIT_ECHO = 16

SUPPRESS_GO_AHEAD = '\x03'

class RetardedTelnetBootstrapProtocol(telnet.Telnet):
    protocol = SillyProtocol

    def connectionMade(self):
        self.transport.write(telnet.IAC + telnet.DO + telnet.LINEMODE)
        self.transport.write(telnet.IAC + telnet.WILL + telnet.ECHO)
        p = self.protocol()
        p.makeConnection(self)
        self.chainedProtocol = p

    def iac_WILL(self, feature):
        if feature == telnet.LINEMODE:
            self.write(telnet.IAC + telnet.SB + telnet.LINEMODE + MODE + chr(TRAPSIG) + telnet.IAC + telnet.SE)
        elif feature == telnet.ECHO:
            self.write(telnet.IAC + telnet.DONT + telnet.ECHO)

    def iac_WONT(self, feature):
        pass

    def iac_DO(self, feature):
        if feature == telnet.GA:
            self.write(telnet.IAC + telnet.WILL + SUPPRESS_GO_AHEAD)

    def iac_DONT(self, feature):
        pass

    def processChunk(self, bytes):
        self.chainedProtocol.dataReceived(bytes)

def makeService(args):
    f = protocol.ServerFactory()
    f.protocol = RetardedTelnetBootstrapProtocol
    s = internet.TCPServer(args['port'], f)
    return s

application = service.Application("Insults Demo App")
makeService({'port': 6464}).setServiceParent(application)