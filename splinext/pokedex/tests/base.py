"""Pyramid application test package

This module provides the base testing objects.
"""

# Shiv to make Unicode test docstrings print correctly; forces stderr to be
# utf8 (or whatever LANG says)
import locale, unittest
enc = locale.getpreferredencoding()
def new_writeln(self, arg=None):
    if arg:
        if isinstance(arg, unicode):
            self.write(arg.encode(enc))
        else:
            self.write(arg)
    self.write('\n')
try:
    unittest._WritelnDecorator.writeln = new_writeln
except AttributeError:
    unittest.runner._WritelnDecorator.writeln = new_writeln

import unittest

import pyramid.paster
import pyramid.testing
from webob.multidict import MultiDict
#import webtest

from splinext.pokedex import db
from splinext.pokedex import pyramidapp

__all__ = ['TestController', 'TestCase', 'PlainTestCase']

INI_FILE = 'test.ini' # XXX make configurable
settings = pyramid.paster.get_appsettings(INI_FILE, name='main')
global_config = {'__file__': INI_FILE}

class TestController(unittest.TestCase):
    """A TestCase that creates a full-blown app for functional testing"""
    def __init__(self, *args, **kwargs):
        app = pyramidapp.main(global_config, **settings)
        self.app = webtest.TestApp(app)

        unittest.TestCase.__init__(self, *args, **kwargs)

class TestCase(unittest.TestCase):
    """A TestCase that does pyramid testing setup"""

    @classmethod
    def setUpClass(cls):
        db.connect(settings)

    def setUp(self):
        self.config = pyramid.testing.setUp()

    def tearDown(self):
        pyramid.testing.tearDown()

class PlainTestCase(object):

    @classmethod
    def setUpClass(cls):
        db.connect(settings)

    def setUp(self):
        self.config = pyramid.testing.setUp()

    def tearDown(self):
        pyramid.testing.tearDown()


class TemplateContext(object):
    pass

def request_factory(matchdict={}, params={}):
    request = pyramid.testing.DummyRequest()
    request.tmpl_context = TemplateContext()
    request.matchdict = MultiDict(matchdict)
    request.params = MultiDict()
    for k, vs in params.iteritems():
        if type(vs) is list:
            for v in vs:
                request.params.add(k, v)
        else:
            request.params.add(k, vs)
    return request
