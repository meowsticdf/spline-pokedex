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

__all__ = ['TestCase', 'PlainTestCase']

INI_FILE = 'test.ini' # XXX make configurable
settings = pyramid.paster.get_appsettings(INI_FILE, name='main')
global_config = {'__file__': INI_FILE}

class TestCase(unittest.TestCase):
    """A TestCase that does pyramid testing setup"""

    @classmethod
    def setUpClass(cls):
        db.connect(settings)

    def setUp(self):
        self.config = pyramid.testing.setUp()
        self.config.add_subscriber(pyramidapp.add_javascripts_subscriber)
        self.config.add_subscriber(pyramidapp.add_game_language_subscriber)
        set_up_routes(self.config)

    def tearDown(self):
        pyramid.testing.tearDown()

class PlainTestCase(object):
    """A TestCase that does pyramid testing setup but doesn't inherit from unittest.TestCase."""

    @classmethod
    def setUpClass(cls):
        db.connect(settings)

    def setUp(self):
        self.config = pyramid.testing.setUp()
        self.config.add_subscriber(pyramidapp.add_javascripts_subscriber)
        self.config.add_subscriber(pyramidapp.add_game_language_subscriber)
        set_up_routes(self.config)

    def tearDown(self):
        pyramid.testing.tearDown()

def set_up_routes(config):
    # pokedex
    config.add_route('dex/lookup', '/dex/lookup')
    config.add_route('dex/suggest', '/dex/suggest')
    config.add_route('dex/parse_size', '/dex/parse_size')
    config.add_route('dex/media', '/dex/media/*subpath')

    # These are more specific than the general pages below, so must be first
    config.add_route('dex_search/move_search', '/dex/moves/search')
    config.add_route('dex_search/pokemon_search', '/dex/pokemon/search')

    config.add_route('dex/abilities', '/dex/abilities/{name}')
    config.add_route('dex/item_pockets', '/dex/items/{pocket}')
    config.add_route('dex/items', '/dex/items/{pocket}/{name}')
    config.add_route('dex/locations', '/dex/locations/{name}')
    config.add_route('dex/moves', '/dex/moves/{name}')
    config.add_route('dex/natures', '/dex/natures/{name}')
    config.add_route('dex/pokemon', '/dex/pokemon/{name}')
    config.add_route('dex/pokemon_flavor', '/dex/pokemon/{name}/flavor')
    config.add_route('dex/pokemon_locations', '/dex/pokemon/{name}/locations')
    config.add_route('dex/types', '/dex/types/{name}')

    config.add_route('dex/abilities_list', '/dex/abilities')
    config.add_route('dex/items_list', '/dex/items')
    config.add_route('dex/locations_list', '/dex/locations')
    config.add_route('dex/natures_list', '/dex/natures')
    config.add_route('dex/moves_list', '/dex/moves')
    config.add_route('dex/pokemon_list', '/dex/pokemon')
    config.add_route('dex/types_list', '/dex/types')

    config.add_route('dex_gadgets/chain_breeding', '/dex/gadgets/chain_breeding')
    config.add_route('dex_gadgets/compare_pokemon', '/dex/gadgets/compare_pokemon')
    config.add_route('dex_gadgets/capture_rate', '/dex/gadgets/pokeballs')
    config.add_route('dex_gadgets/stat_calculator', '/dex/gadgets/stat_calculator')
    config.add_route('dex_gadgets/whos_that_pokemon', '/dex/gadgets/whos_that_pokemon')

    # Conquest pages; specific first, again
    config.add_route('dex_conquest/abilities', '/dex/conquest/abilities/{name}')
    config.add_route('dex_conquest/kingdoms', '/dex/conquest/kingdoms/{name}')
    config.add_route('dex_conquest/moves', '/dex/conquest/moves/{name}')
    config.add_route('dex_conquest/pokemon', '/dex/conquest/pokemon/{name}')
    config.add_route('dex_conquest/skills', '/dex/conquest/skills/{name}')
    config.add_route('dex_conquest/warriors', '/dex/conquest/warriors/{name}')

    config.add_route('dex_conquest/abilities_list', '/dex/conquest/abilities')
    config.add_route('dex_conquest/kingdoms_list', '/dex/conquest/kingdoms')
    config.add_route('dex_conquest/moves_list', '/dex/conquest/moves')
    config.add_route('dex_conquest/pokemon_list', '/dex/conquest/pokemon')
    config.add_route('dex_conquest/skills_list', '/dex/conquest/skills')
    config.add_route('dex_conquest/warriors_list', '/dex/conquest/warriors')

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
    request.GET = request.params.copy()
    return request
