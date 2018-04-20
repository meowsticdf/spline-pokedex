from pyramid.config import Configurator
from spline.config.middleware import make_app

# https://docs.pylonsproject.org/projects/pyramid-cookbook/en/latest/porting/legacy.html
class LegacyView(object):
    def __init__(self, app):
        self.app = app
    def __call__(self, request):
        return request.get_response(self.app)

def main(global_config, **settings):
    config = Configurator(settings=settings)
    pylonsapp = make_app(global_config, **settings)

    config.add_static_view('static/spline', 'spline:public')
    config.add_static_view('static/pokedex', 'splinext.pokedex:public')
    config.add_static_view('static/local', '../../veekun/public') # XXX
    config.add_static_view('dex/media', '../../pokedex-media/') # XXX

    legacy_view = LegacyView(pylonsapp)
    config.add_view(context='pyramid.exceptions.NotFound', view=legacy_view)
    return config.make_wsgi_app()
