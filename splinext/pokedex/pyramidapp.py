from pyramid.config import Configurator
from pyramid.renderers import render, render_to_response

import spline.lib.helpers
import spline.lib.base

def index_view(request):
    return render_to_response('/index.mako', {}, request=request)

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
    response = request.response
    c.message = request.GET.get('message', response and response.status)
    c.code    = request.GET.get('code',    response and response.status_int)
    c.code = int(c.code)
    return render('error.mako', {}, request=request)

def add_renderer_globals_factory(config):
    def add_renderer_globals(event):
        """A subscriber for ``pyramid.events.BeforeRender`` events.  I add
        some :term:`renderer globals` with values that are familiar to Pylons
        users.
        """
        def fake_url(controller=None, action=None, **kwargs):
            if action == "css":
                return "/css"
            if action and controller:
                return request.url(controller+"/"+action, **kwargs)
            return "/"

        def fake_translate(message, plural=None, n=None, context=None, comment=None):
            return unicode(message)

        renderer_globals = event
        renderer_globals["config"] = config
        renderer_globals["h"] = spline.lib.helpers
        request = event.get("request") or threadlocal.get_current_request()
        if not request:
            return
        renderer_globals["r"] = request
        renderer_globals["c"] = request.tmpl_context
        #renderer_globals["url"] = request.url_generator
        renderer_globals["url"] = fake_url
        renderer_globals["_"] = fake_translate

        request.tmpl_context.links = config['spline.plugins.links']
        request.tmpl_context.javascripts = [
            ('spline', 'lib/jquery-1.7.1.min'),
            ('spline', 'lib/jquery.cookies-2.2.0.min'),
            ('spline', 'lib/jquery.ui-1.8.4.min'),
            ('spline', 'core'),
        ]

        # start timer
        request.tmpl_context.timer = spline.lib.base.ResponseTimer()
    return add_renderer_globals

def main(global_config, **settings):
    local_templates = './templates'
    settings['mako.directories'] = [local_templates, 'splinext.pokedex:templates', 'spline:templates']

    settings['spline.plugins'] = []
    settings['spline.plugins.controllers'] = {}
    settings['spline.plugins.hooks'] = {}
    settings['spline.plugins.widgets'] = {}
    settings['spline.plugins.links'] = {}
    settings['spline.plugins.stylesheets'] = [
        #'reset.mako',
        'layout.mako',
        'pokedex.mako',
        #'pokedex-suggestions.css',
        'sprites.mako',
    ]

    config = Configurator(settings=settings)
    config.include('pyramid_mako')
    config.include('pyramid_debugtoolbar')
    config.add_mako_renderer(".css") # XXX delete

    add_renderer_globals = add_renderer_globals_factory(settings)
    config.add_subscriber(add_renderer_globals, "pyramid.events.BeforeRender")

    ### routes
    # index page
    config.add_route("index", "/")

    # css
    config.add_route("css", "/css")

    # pokedex
    config.add_route('dex/lookup', '/dex/lookup')
    config.add_route('dex/suggest', '/dex/suggest')
    config.add_route('dex/parse_size', '/dex/parse_size')

    # These are more specific than the general pages below, so must be first
    config.add_route('dex_search/move_search', '/dex/moves/search')
    config.add_route('dex_search/pokemon_search', '/dex/pokemon/search')

    config.add_route('dex/abilities', '/dex/abilities/{name}')
    config.add_route('dex/item_pocket', '/dex/items/{pocket}')
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

    ### views

    # static resources
    config.add_static_view('static/spline', 'spline:public')
    config.add_static_view('static/pokedex', 'splinext.pokedex:public')
    config.add_static_view('static/local', '../../veekun/public') # XXX
    config.add_static_view('dex/media', '../../pokedex-media/') # XXX

    # index & css
    config.add_view(index_view, route_name="index")
    config.add_view(css_view, route_name="css")

    # error pages
    #config.add_view(context='pyramid.httpexceptions.HTTPForbidden', view=error_view)
    #config.add_view(context='pyramid.httpexceptions.HTTPNotFound', view=error_view)

    return config.make_wsgi_app()
