
# System Imports
import string, time, types, traceback, copy, pprint, sys, os
from cStringIO import StringIO

# Twisted Imports
from twisted.python import defer, rebuild, reflect
from twisted.protocols import http

# Sibling Imports
import html, resource, static, error
from server import NOT_DONE_YET

"""A twisted web component framework.
"""

class Widget:
    def display(self, request):
        raise NotImplementedError("twisted.web.widgets.Widget.display")


class StreamWidget(Widget):
    def stream(self, write, request):
        raise NotImplementedError("twisted.web.widgets.StringWidget.stream")

    def display(self, request):
        io = StringIO()
        try:
            self.stream(io.write, request)
            return [io.getvalue()]
        except:
            io = StringIO()
            traceback.print_exc(file=io)
            return [html.PRE(io.getvalue())]


class Presentation(Widget):
    template = '''
    hello %%%%world%%%%
    '''
    def __init__(self, template=None, filename=None):
        if filename:
            self.template = open(filename).read()
        elif template:
            self.template = template
        self.variables = {}
        self.tmpl = string.split(self.template, "%%%%")

    def addClassVars(self, namespace, Class):
        for base in Class.__bases__:
            # Traverse only superclasses that know about Presentation.
            if issubclass(base, Presentation) and base is not Presentation:
                self.addClassVars(namespace, base)
        # 'lower' classes in the class heirarchy take precedence.
        for k in Class.__dict__.keys():
            namespace[k] = getattr(self, k)

    def addVariables(self, namespace, request):
        self.addClassVars(namespace, self.__class__)

    def display(self, request):
        tm = []
        flip = 0
        namespace = {}
        self.addVariables(namespace, request)
        # This variable may not be obscured...
        namespace['request'] = request
        for elem in self.tmpl:
            flip = not flip
            if flip:
                tm.append(elem)
            else:
                try:
                    x = eval(elem, namespace, namespace)
                except:
                    io = StringIO()
                    io.write("Traceback evaluating code in %s:" % str(self.__class__))
                    traceback.print_exc(file = io)
                    tm.append(html.PRE(io.getvalue()))
                else:
                    if isinstance(x, types.ListType):
                        tm.extend(x)
                    elif isinstance(x, Widget):
                        tm.extend(x.display(request))
                    else:
                        # Only two allowed types here should be deferred and
                        # string.
                        tm.append(x)
        return tm


def htmlFor_hidden(write, name, value):
    write('<INPUT TYPE="hidden" NAME="%s" VALUE="%s">' % (name, value))
def htmlFor_file(write, name, value):
    write('<INPUT SIZE=60 TYPE="file" NAME="%s">' % name)
def htmlFor_string(write, name, value):
    write('<INPUT SIZE=60 TYPE="text" NAME="%s" VALUE="%s">' % (name, value))
def htmlFor_password(write, name, value):
    write('<INPUT SIZE=60 TYPE="password" NAME=%s>' % name)
def htmlFor_text(write, name, value):
    write('<TEXTAREA COLS="60" ROWS="10" NAME="%s" WRAP="virtual">%s</textarea>' % (name, value))
def htmlFor_menu(write, name, value):
    "Value of the format (NAME, [OPTION, OPTION, OPTION])"
    write('<SELECT NAME="%s">\n' % name)
    for item in value:
        write("<OPTION>\n%s\n" % item)
    write("</select>")


class FormInputError(Exception):
    pass

class Form(StreamWidget):

    formGen = {
        'hidden': htmlFor_hidden,
        'file': htmlFor_file,
        'string': htmlFor_string,
        'int': htmlFor_string,
        'text': htmlFor_text,
        'menu': htmlFor_menu,
        'password': htmlFor_password
    }

    formParse = {
        'int': int
    }

    formFields = [
    ]

    def getFormFields(self, request):
        return self.formFields

    submitName = 'OK'

    def format(self, form, write):
        write('<FORM ENCTYPE="multipart/form-data" METHOD="post">\n'
              '<TABLE BORDER="0">\n')
        for inputType, displayName, inputName, inputValue in form:
            write('<TR>\n<TD ALIGN="right" VALIGN="top"><B>%s</b></td>\n'
                  '<TD VALIGN="%s">\n' %
                  (displayName, ((inputType == 'text') and 'top') or 'middle'))
            self.formGen[inputType](write, inputName, inputValue)
            write('</td>\n</tr>\n')
        write('<TR><TD></TD><TD ALIGN="center">\n'
              '<INPUT TYPE="submit" NAME="submit" VALUE="%s">\n'
              '</td></tr>\n</table>\n'
              '<INPUT TYPE="hidden" NAME="__formtype__" VALUE="%s">\n'
              '</form>\n' % (self.submitName, str(self.__class__)))


    def process(self, write, request, **kw):
        write(pprint.PrettyPrinter().pformat(kw))

    def doProcess(self, form, write, request):
        args = request.args
        kw = {}
        for inputType, displayName, inputName, inputValue in form:
            if not args.has_key(inputName):
                raise FormInputError("missing field %s." % repr(inputName))
            formData = args[inputName]
            del args[inputName]
            if not len(formData) == 1:
                raise FormInputError("multiple values for field %s." %repr(inputName))
            formData = formData[0]
            method = self.formParse.get(inputType)
            if method:
                formData = method(formData)
            kw[inputName] = formData
        for field in ['submit', '__formtype__']:
            if args.has_key(field):
                del args[field]
        if args:
            raise FormInputError("unknown fields" % repr(args))
        apply(self.process, (write, request), kw)

    def stream(self, write, request):
        args = request.args
        form = self.getFormFields(request)
        if args and args.has_key('__formtype__') and args['__formtype__'][0] == str(self.__class__):
            try:
                return self.doProcess(write, request)
            except FormInputError, fie:
                write('<FONT COLOR=RED><B><I>%s</i></b></font><br>\n' % str(fie))
        self.format(write)


class TextWidget(Widget):
    def __init__(self, text):
        self.text = text

    def display(self, request):
        return [self.text]

class TextDeferred(Widget):
    def __init__(self, text):
        self.text = text

    def display(self, request):
        d = defer.Deferred()
        d.callback(self.text)
        return [d]

class Time(Widget):
    def display(self, request):
        return [time.ctime(time.time())]

class Container(Widget):
    def __init__(self, *widgets):
        self.widgets = widgets

    def display(self, request):
        value = []
        for widget in self.widgets:
            d = widget.display(request)
            value.extend(d)
        return value

class RenderSession:
    def __init__(self, lst, request):
        self.lst = lst
        self.request = request
        self.position = 0
        pos = 0
        toArm = []
        for item in lst:
            if isinstance(item, defer.Deferred):
                args = (pos,)
                item.addCallbacks(self.callback, self.errback,
                                  callbackArgs=args, errbackArgs=args)
                toArm.append(item)
            pos = pos + 1
        self.keepRendering()
        # print "RENDER: DONE WITH INITIAL PASS"
        for item in toArm:
            item.arm()

    def callback(self, result, position):
        self.lst[position] = result
        self.keepRendering()

    def errback(self, error, position):
        self.lst[position] = error
        self.keepRendering()

    def keepRendering(self):
        assert self.lst is not None, "This shouldn't happen."
        while 1:
            item = self.lst[self.position]
            if isinstance(item, types.StringType):
                self.request.write(item)
            elif isinstance(item, defer.Deferred):
                return
            else:
                self.request.write("RENDERING UNKNOWN: %s" % str(item))
            self.position = self.position + 1
            if self.position == len(self.lst):
                self.lst = None
                self.request.finish()
                return


class Page(resource.Resource, Presentation):

    def __init__(self):
        resource.Resource.__init__(self)
        Presentation.__init__(self)

    def render(self, request):
        RenderSession(self.display(request), request)
        return NOT_DONE_YET


class WidgetPage(Page):

    stylesheet = '''
    A
    {
        font-family: Lucida, Verdana, Helvetica, Arial;
        color: #336699;
        text-decoration: none;
    }

    TH
    {
        font-family: Lucida, Verdana, Helvetica, Arial;
        font-weight: bold;
        text-decoration: none;
    }

    PRE, CODE
    {
        font-family: Courier New, Courier;
    }

    P, BODY, TD, OL, UL, MENU, BLOCKQUOTE, DIV
    {
        font-family: Lucida, Verdana, Helvetica, Arial;
        color: #000000;
    }
    '''

    template = '''
    <HTML>
    <STYLE>
    %%%%stylesheet%%%%
    </style>
    <HEAD><TITLE>%%%%title%%%%</title></head>
    <BODY>
    <H1>%%%%title%%%%</h1>
    %%%%widget%%%%
    </body>
    </html>
    '''

    title = 'No Title'
    widget = 'No Widget'

    def __init__(self, widget):
        Page.__init__(self)
        self.widget = widget
        self.title = getattr(widget, 'title', None) or str(widget.__class__)
        if hasattr(widget, 'stylesheet'):
            self.stylesheet = widget.stylesheet

    def render(self, request):
        RenderSession(self.display(request), request)
        return NOT_DONE_YET

class Gadget(resource.Resource):
    widgets = {
    }
    files = [
    ]
    modules = [
    ]
    page = WidgetPage

    def getChild(self, path, request):
        if path == '':
            path = 'index'
        widget = self.widgets.get(path)
        if widget:
            if isinstance(widget, resource.Resource):
                return widget
            else:
                return self.page(widget)
        elif path in self.files:
            prefix = getattr(sys.modules[self.__module__], '__file__', '')
            if prefix:
                prefix = os.path.abspath(os.path.dirname(prefix))
            return static.File(os.path.join(prefix, path))
        elif path == '__reload__':
            return self.page(Reloader(map(reflect.named_module, [self.__module__] + self.modules)))
        else:
            return error.NoResource()


class TitleBox(Presentation):

    template = '''\
    <table cellpadding="1" cellspacing="0" border="0"><tr>\
    <td bgcolor="#000000"><center><font color="#FFFFFF">%%%%title%%%%</font\
    ></center><table cellpadding="3" cellspacing="0" border="0"><tr>\
    <td bgcolor="#FFFFFF"><font color="#000000">%%%%widget%%%%</font></td>\
    </tr></table></td></tr></table>\
    '''

    title = 'No Title'
    widget = 'No Widget'

    def __init__(self, title, widget):
        """Wrap a widget with a given title.
        """
        self.widget = widget
        self.title = title


class Reloader(Presentation):
    template = '''
    Reloading...
    <ul>
    %%%%reload(request)%%%%
    </ul> ... reloaded!
    '''
    def __init__(self, modules):
        Presentation.__init__(self)
        self.modules = modules

    def reload(self, request):
        request.setHeader("location", "..")
        request.setResponseCode(http.MOVED_PERMANENTLY)
        x = []
        write = x.append
        for module in self.modules:
            rebuild.rebuild(module)
            write('<li>reloaded %s<br>' % module.__name__)
        return x

class Sidebar(StreamWidget):
    bar = [
        ['Twisted',
            ['mirror', 'http://coopweb.org/ssd/twisted/'],
            ['mailing list', 'cgi-bin/mailman/listinfo/twisted-python']
        ]
    ]

    headingColor = 'ffffff'
    headingTextColor = '000000'
    activeHeadingColor = '000000'
    activeHeadingTextColor = 'ffffff'
    sectionColor = '000088'
    sectionTextColor = '008888'
    activeSectionColor = '0000ff'
    activeSectionTextColor = '00ffff'

    def __init__(self, highlightHeading, highlightSection):
        self.highlightHeading = highlightHeading
        self.highlightSection = highlightSection

    def getList(self):
        return self.bar

    def stream(self, write, request):
        write("<TABLE width=120 cellspacing=1 cellpadding=1 border=0>")
        for each in self.getList():
            if each[0] == self.highlightHeading:
                headingColor = self.activeHeadingColor
                headingTextColor = self.activeHeadingTextColor
                canHighlight = 1
            else:
                headingColor = self.headingColor
                headingTextColor = self.headingTextColor
                canHighlight = 0
            write('<TR><TD colspan=2 bgcolor="#%s"><FONT COLOR="%s"><b>%s</b>'
                  '</font></td></td></tr>\n' % (headingColor, headingTextColor, each[0]))
            for name, link in each[1:]:
                if canHighlight and (name == self.highlightSection):
                    sectionColor = self.activeSectionColor
                    sectionTextColor = self.activeSectionTextColor
                else:
                    sectionColor = self.sectionColor
                    sectionTextColor = self.sectionTextColor
                write('<TR><td align=right bgcolor="#%s" width=6>-</td>'
                      '<TD bgcolor="#%s"><A HREF="%s"><FONT COLOR="#%s">%s'
                      '</font></a></td></tr>'
                       % (sectionColor, sectionColor, request.sibLink(link), sectionTextColor, name))
        write("</table>")

