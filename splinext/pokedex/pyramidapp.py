# encoding: utf-8
import os
import warnings

from pyramid.config import Configurator
import pyramid.httpexceptions as exc
from pyramid.renderers import render, render_to_response, JSONP
from pyramid.response import Response
import pyramid.settings
import pyramid.static
from pyramid import threadlocal

from frontpage.controllers.frontpage import FrontPageController
from frontpage import load_sources_hook as frontpage_config

import beaker.cache
import beaker.util

import pokedex.db.markdown

from . import db
from . import lib
from . import splinehelpers
from . import helpers

def index_view(request):
    FrontPageController(request).index()

    return render_to_response('/index.mako', {}, request=request)

def content_view(request):
    return {}

def css_view(request):
    """Returns all the CSS, concatenated."""

    stylesheets = []
    for css_file in request.registry.settings['spline.plugins.stylesheets']:
        stylesheets.append(render("/css/%s" % css_file, {}, request=request))

    response = request.response
    response.content_type = 'text/css'
    response.charset = 'utf-8'
    response.text = u'\n'.join(stylesheets)
    return response

def error_view(request):
    c = request.tmpl_context
    error = request.exception or request.context
    if isinstance(error, exc.HTTPException):
        response = Response(status=error.code)
    else:
        response = Response(status=500)
    c.code = response.status_code
    c.message = response.status
    return render_to_response('error.mako', {}, request=request, response=response)

def add_renderer_globals(event):
    """A subscriber for ``pyramid.events.BeforeRender`` events.  I add
    some :term:`renderer globals` with values that are familiar to Pylons
    users.
    """
    def fake_url(controller=None, action=None, **kwargs):
        if action == "css":
            return "/css"
        if action and controller:
            path = {}
            for key in 'name', 'pocket', 'subpath':
                if key in kwargs:
                    path[key] = kwargs.pop(key)
            path['_query'] = dict((k,v) for k,v in kwargs.items() if v is not None)
            return request.route_path(controller+"/"+action, **path)
        if controller and controller.startswith("/"):
            return controller
        return "/unknown"

    def fake_url_current(**kwargs):
        path = {}
        # XXX request.matchdict?
        if 'name' in kwargs:
            path['name'] = kwargs.pop('name')
        if 'action' in kwargs:
            path['_route_name'] = 'dex/'+kwargs.pop('action')
        path['_query'] = dict((k,v) for k,v in kwargs.items() if v is not None)
        return request.current_route_path(**path)

    def fake_translate(message, plural=None, n=None, context=None, comment=None):
        return unicode(message)

    renderer_globals = event
    request = event.get("request") #or threadlocal.get_current_request()
    if not request:
        return
    config = request.registry.settings
    renderer_globals["config"] = config
    renderer_globals["h"] = splinehelpers
    renderer_globals["r"] = request
    renderer_globals["c"] = request.tmpl_context
    #renderer_globals["url"] = request.url_generator
    renderer_globals["url"] = fake_url
    fake_url.current = fake_url_current
    renderer_globals["_"] = fake_translate
    renderer_globals["flash"] = lib.Flash(request.session)

    request.tmpl_context.links = config['spline.plugins.links']

    # start timer
    request.tmpl_context.timer = lib.ResponseTimer()

def add_javascripts_subscriber(event):
    """A subscriber which sets the request.tmpl_context.javascript variable"""
    c = event.request.tmpl_context
    c.javascripts = [
        ('spline', 'lib/jquery-1.7.1.min'),
        ('spline', 'lib/jquery.cookies-2.2.0.min'),
        ('spline', 'lib/jquery.ui-1.8.4.min'),
        ('spline', 'core'),
        ('pokedex', 'pokedex-suggestions'),
        ('pokedex', 'pokedex'), # XXX only on main pokedex pages
    ]

def add_game_language_subscriber(event):
    """A subscriber which sets request.tmpl_context.game_language before views run"""
    request = event.request
    # TODO: look up game language from a cookie or something
    en = db.get_by_identifier_query(db.t.Language, u'en').first()
    request.tmpl_context.game_language = en

class SplineExtension(pokedex.db.markdown.PokedexLinkExtension):
    """Extend markdown to turn [Eevee]{pokemon:eevee} into a link in effects
    and descriptions. """
    def object_url(self, category, obj):
        # XXX(pyramid): it would be nice to not use threadlocal here
        request = threadlocal.get_current_request()
        if request:
            return helpers.resource_url(request, obj)
        return None

class cache_tween_factory(object):
    """Constructs a beaker.cache.CacheManager from the application settings
    and stores it in the wsgi environment as request.environ['beaker.cache']"""

    # It would be nice if pyramid_beaker did this for us but all it does
    # is configure cache regions, which we don't use.

    def __init__(self, handler, registry):
        self.handler = handler
        self.cache_settings = beaker.util.parse_cache_config_options(registry.settings)
        self.cache_manager = beaker.cache.CacheManager(**self.cache_settings)

    def __call__(self, request):
        request.environ['beaker.cache'] = self.cache_manager
        return self.handler(request)


def main(global_config, **settings):
    config_root = os.path.dirname(global_config['__file__'])
    local_template_dir = os.path.join(config_root, 'templates')
    local_content_dir = os.path.join(config_root, 'content')
    settings['mako.directories'] = [
        local_template_dir,
        'splinext.pokedex:templates',
        local_content_dir,
        'splinext.pokedex:content',
        'frontpage:templates',
    ]

    settings['spline.plugins'] = ['frontpage']
    settings['spline.plugins.controllers'] = {}
    settings['spline.plugins.hooks'] = {}
    settings['spline.plugins.widgets'] = {}
    settings['spline.plugins.links'] = []
    settings['spline.plugins.stylesheets'] = [
        'reset.mako',
        'layout.mako',
        'pokedex.mako',
        'sprites.mako',
    ]

    frontpage_config(settings)

    widgets = [
            ('page_header', 'widgets/pokedex_lookup.mako'),
            ('head_tag',    'widgets/pokedex_suggestion_css.mako'),

            #('before_content', 'widgets/before_content.mako'),
            ('head_tag',    'widgets/head_tag.mako'),
            ('page_header', 'widgets/page_header/logo.mako'),
    ]
    for name, path in widgets:
        x = settings['spline.plugins.widgets'].setdefault(name, {3:[]})
        x[3].append(path)

    config = Configurator(settings=settings)
    config.include('pyramid_tm')
    config.include('pyramid_mako')
    config.include('pyramid_beaker')
    config.include('pyramid_debugtoolbar')

    config.add_renderer('jsonp', JSONP(param_name='callback'))
    config.add_mako_renderer('.html', settings_prefix='mako.') # for content pages

    config.add_subscriber(add_renderer_globals, "pyramid.events.BeforeRender")
    config.add_subscriber(add_game_language_subscriber, "pyramid.events.NewRequest")
    config.add_subscriber(add_javascripts_subscriber, "pyramid.events.NewRequest")

    ### caching
    config.add_tween('splinext.pokedex.pyramidapp.cache_tween_factory')

    ### routes
    # index page
    config.add_route("index", "/")

    # css
    config.add_route("css", "/css")

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

    config.add_route('static', '/static/*subpath', static=True)

    ### views

    # static resources
    #config.add_static_view('static/spline', 'spline:public')
    config.add_static_view('static/spline', '../../../spline/spline/public') # XXX
    config.add_static_view('static/pokedex', 'splinext.pokedex:public')
    config.add_static_view('static/local', os.path.join(config_root, './public')) # XXX

    media_root = settings.get('spline-pokedex.media_directory', None)
    if media_root:
        config.add_view(pyramid.static.static_view(media_root, use_subpath=True), route_name='dex/media')
    else:
        warnings.warn("No media_directory found; you may want to clone pokedex-media.git")


    # index & css
    config.add_view(index_view, route_name="index")
    config.add_view(css_view, route_name="css")

    # lookup
    config.add_view(route_name='dex/lookup', view='splinext.pokedex.views.lookup:lookup', renderer='pokedex/lookup_results.mako')
    config.add_view(route_name='dex/suggest', view='splinext.pokedex.views.lookup:suggest', renderer='jsonp')

    # json
    config.add_view(route_name='dex/parse_size', view='splinext.pokedex.views.pokemon:parse_size_view', renderer='json')

    # main dex pages
    config.add_view(route_name='dex/abilities', view='splinext.pokedex.views.abilities:ability_view', renderer='pokedex/ability.mako')
    config.add_view(route_name='dex/abilities_list', view='splinext.pokedex.views.abilities:ability_list', renderer='pokedex/ability_list.mako')
    config.add_view(route_name='dex/locations', view='splinext.pokedex.views.locations:location_view', renderer='pokedex/location.mako')
    config.add_view(route_name='dex/locations_list', view='splinext.pokedex.views.locations:location_list', renderer='pokedex/location_list.mako')
    config.add_view(route_name='dex/items', view='splinext.pokedex.views.items:item_view', renderer='pokedex/item.mako')
    config.add_view(route_name='dex/item_pockets', view='splinext.pokedex.views.items:pocket_view', renderer='pokedex/item_pockets.mako')
    config.add_view(route_name='dex/items_list', view='splinext.pokedex.views.items:item_list', renderer='pokedex/item_list.mako')
    config.add_view(route_name='dex/moves', view='splinext.pokedex.views.moves:move_view', renderer='pokedex/move.mako')
    config.add_view(route_name='dex/moves_list', view='splinext.pokedex.views.moves:move_list', renderer='pokedex/move_list.mako')
    config.add_view(route_name='dex/natures', view='splinext.pokedex.views.natures:nature_view', renderer='pokedex/nature.mako')
    config.add_view(route_name='dex/natures_list', view='splinext.pokedex.views.natures:natures_list', renderer='pokedex/nature_list.mako')
    config.add_view(route_name='dex/pokemon', view='splinext.pokedex.views.pokemon:pokemon_view', renderer='pokedex/pokemon.mako')
    config.add_view(route_name='dex/pokemon_list', view='splinext.pokedex.views.pokemon:pokemon_list', renderer='pokedex/pokemon_list.mako')
    config.add_view(route_name='dex/pokemon_flavor', view='splinext.pokedex.views.pokemon:pokemon_flavor_view', renderer='pokedex/pokemon_flavor.mako')
    config.add_view(route_name='dex/pokemon_locations', view='splinext.pokedex.views.pokemon:pokemon_locations_view', renderer='pokedex/pokemon_locations.mako')
    config.add_view(route_name='dex/types', view='splinext.pokedex.views.types:type_view', renderer='pokedex/type.mako')
    config.add_view(route_name='dex/types_list', view='splinext.pokedex.views.types:type_list', renderer='pokedex/type_list.mako')

    # search
    config.add_view(route_name='dex_search/pokemon_search', view='splinext.pokedex.views.search:pokemon_search', renderer='pokedex/search/pokemon.mako')
    config.add_view(route_name='dex_search/move_search', view='splinext.pokedex.views.search:move_search', renderer='pokedex/search/moves.mako')

    # gadgets
    config.add_view(route_name='dex_gadgets/capture_rate', view='splinext.pokedex.views.gadgets:capture_rate', renderer='pokedex/gadgets/capture_rate.mako')
    config.add_view(route_name='dex_gadgets/chain_breeding', view='splinext.pokedex.views.gadgets:chain_breeding', renderer='/pokedex/gadgets/chain_breeding.mako')
    config.add_view(route_name='dex_gadgets/compare_pokemon', view='splinext.pokedex.views.gadgets:compare_pokemon', renderer='pokedex/gadgets/compare_pokemon.mako')
    config.add_view(route_name='dex_gadgets/stat_calculator', view='splinext.pokedex.views.gadgets:stat_calculator', renderer='pokedex/gadgets/stat_calculator.mako')

    # conquest

    config.add_view(route_name='dex_conquest/abilities', view='splinext.pokedex.views.conquest:ability_view', renderer='pokedex/conquest/ability.mako')
    config.add_view(route_name='dex_conquest/kingdoms', view='splinext.pokedex.views.conquest:kingdom_view', renderer='pokedex/conquest/kingdom.mako')
    config.add_view(route_name='dex_conquest/moves', view='splinext.pokedex.views.conquest:move_view', renderer='pokedex/conquest/move.mako')
    config.add_view(route_name='dex_conquest/pokemon', view='splinext.pokedex.views.conquest:pokemon_view', renderer='pokedex/conquest/pokemon.mako')
    config.add_view(route_name='dex_conquest/skills', view='splinext.pokedex.views.conquest:skill_view', renderer='pokedex/conquest/skill.mako')
    config.add_view(route_name='dex_conquest/warriors', view='splinext.pokedex.views.conquest:warrior_view', renderer='pokedex/conquest/warrior.mako')

    config.add_view(route_name='dex_conquest/abilities_list', view='splinext.pokedex.views.conquest:ability_list', renderer='pokedex/conquest/ability_list.mako')
    config.add_view(route_name='dex_conquest/kingdoms_list', view='splinext.pokedex.views.conquest:kingdom_list', renderer='pokedex/conquest/kingdom_list.mako')
    config.add_view(route_name='dex_conquest/moves_list', view='splinext.pokedex.views.conquest:move_list', renderer='pokedex/conquest/move_list.mako')
    config.add_view(route_name='dex_conquest/pokemon_list', view='splinext.pokedex.views.conquest:pokemon_list', renderer='pokedex/conquest/pokemon_list.mako')
    config.add_view(route_name='dex_conquest/skills_list', view='splinext.pokedex.views.conquest:skill_list', renderer='pokedex/conquest/skill_list.mako')
    config.add_view(route_name='dex_conquest/warriors_list', view='splinext.pokedex.views.conquest:warrior_list', renderer='pokedex/conquest/warrior_list.mako')

    # content pages
    def add_content_page(path, template):
        route_name = path
        config.add_route(route_name, path)
        config.add_view(content_view, route_name=route_name, renderer=template)

    add_content_page("/dex", "dex.html")
    add_content_page("/dex/conquest", "dex/conquest.html")
    add_content_page("/dex/downloads", "dex/downloads.html")
    add_content_page("/dex/history", "dex/history.html")
    add_content_page("/about", "about.html")
    add_content_page("/chat", "chat.html")
    add_content_page("/props", "props.html")
    add_content_page("/link", "link.html")

    # error pages
    # handle 400, 401, 403, 404, and 500
    config.add_notfound_view(error_view) # 404
    config.add_forbidden_view(error_view) # 403
    config.add_exception_view(error_view, context='pyramid.httpexceptions.HTTPBadRequest') # 400
    config.add_exception_view(error_view, context='pyramid.httpexceptions.HTTPUnauthorized') # 401
    config.add_exception_view(error_view, context='pyramid.httpexceptions.HTTPInternalServerError') # 500

    # Install a generic error handler if the debugtoolbar is not enabled
    # If it is enabled, we'd rather let it display a traceback
    if not pyramid.settings.asbool(settings.get('debugtoolbar.enabled', True)):
        config.add_exception_view(error_view, context=Exception) # catch-all

    ### links

    Link = lib.Link
    TranslatablePluginLink = Link # XXX
    _ = lambda x: x
    links = [
        Link(u'veekun', '/', children=[
            Link(u'', None, children=[
                Link(u'About + contact',  '/about'),
                Link(u'Chat',             '/chat'),
                Link(u'Credits',          '/props'),
                Link(u'Link or embed veekun', '/link'),
                Link(u'Pokédex history',  '/dex/history'),
            ]),
        ]),
        TranslatablePluginLink(_(u'Pokédex'), '/dex', children=[
            TranslatablePluginLink(_(u'Core pages'), None, children=[
                TranslatablePluginLink(_(u'Pokémon'), 'dex/pokemon_list', i18n_context='plural', children=[
                    TranslatablePluginLink(_(u'Awesome search'), 'dex_search/pokemon_search'),
                ]),
                TranslatablePluginLink(_(u'Moves'), 'dex/moves_list', children=[
                    TranslatablePluginLink(_(u'Awesome search'), 'dex_search/move_search'),
                ]),
                TranslatablePluginLink(_(u'Types'), 'dex/types_list'),
                TranslatablePluginLink(_(u'Abilities'), 'dex/abilities_list'),
                TranslatablePluginLink(_(u'Items'), 'dex/items_list'),
                TranslatablePluginLink(_(u'Natures'), 'dex/natures_list'),
                TranslatablePluginLink(_(u'Locations'), 'dex/locations_list'),
            ]),
            TranslatablePluginLink(_(u'Gadgets'), None, children=[
                TranslatablePluginLink(_(u'Compare Pokémon'), 'dex_gadgets/compare_pokemon'),
                TranslatablePluginLink(_(u'Pokéball performance'), 'dex_gadgets/capture_rate'),
                TranslatablePluginLink(_(u'Stat calculator'), 'dex_gadgets/stat_calculator'),
            ]),
            TranslatablePluginLink(_(u'Conquest'), '/dex/conquest', children=[
                TranslatablePluginLink(_(u'Pokémon'), 'dex_conquest/pokemon_list'),
                TranslatablePluginLink(_(u'Warriors'), 'dex_conquest/warriors_list'),
                TranslatablePluginLink(_(u'Abilties'), 'dex_conquest/abilities_list'),
                TranslatablePluginLink(_(u'Moves'), 'dex_conquest/moves_list'),
                TranslatablePluginLink(_(u'Warrior Skills'), 'dex_conquest/skills_list')
            ]),
            TranslatablePluginLink(_(u'Etc.'), None, children=[
                TranslatablePluginLink(_(u'Downloads'), '/dex/downloads'),
            ]),
        ]),
    ]
    settings['spline.plugins.links'].extend(links)

    # Connect to ye olde database (and lookup index)
    db.connect(settings)

    # Extend the pokedex code's default markdown rendering
    db.pokedex_session.configure(markdown_extension_class=SplineExtension)

    # XXX
    splinehelpers.pokedex = helpers

    return config.make_wsgi_app()
