"""Some utilities for caching pages."""

import zlib

from beaker.util import func_namespace
from mako.runtime import capture

def cache_content(request, key, do_work):
    """Argh!

    Okay, so.  Use this when you want to cache the BODY of a page but not
    the CHROME (i.e., wrapper or base or whatever).

    ``request``
        The pyramid.request.Request object for the current request.

    ``key``
        The key that uniquely identifies this particular rendering of this
        page content.

    ``do_work``
        Some function that will stuff a bunch of expensive data in c.  This
        will only be called if the page hasn't yet been cached.  It'll be
        passed the key.

        The name and module of this function will be used as part of the cache
        key.

    Also, DO NOT FORGET TO wrap the cachable part of your template in a
    <%lib:cache_content> tag, or nothing will get cached!

    If a page body is pulled from cache, c.timer.from_cache will be set to
    True.  If the page had to be generated, it will be set to False.  (If
    this function wasn't involved at all, it will be set to None.)
    """
    cache = request.environ.get('beaker.cache', None)
    c = request.tmpl_context

    # Content needs to be cached per-language
    # TODO(pyramid)
    #key = u"{0}/{1}".format(key, c.lang)

    key += u';' + c.game_language.identifier
    if request.session.get('cheat_obdurate', False):
        key += u';obdurate'

    # If the cache isn't configured for whatever reason (such as when we're
    # running in a test environment), just skip it.
    if cache is None:
        # call do_work immediately so that it isn't skipped during testing
        # (since tests don't call the renderer)
        do_work(request, key)
        def skip_cache(context, mako_def):
            mako_def.body()
        c._cache_me = skip_cache
        return

    namespace = func_namespace(do_work)
    # Cache for...  ten hours?  Sure, whatever
    # TODO: use get_cache_region instead
    content_cache = cache.get_cache('content_cache:' + namespace,
                                    expiretime=36000)

    # XXX This is dumb.  Caches don't actually respect the 'enabled'
    # setting, so we gotta fake it.
    if not content_cache.nsargs.get('enabled', True):
        def skip_cache(context, mako_def):
            do_work(request, key)
            mako_def.body()
        c._cache_me = skip_cache
        return

    # These pages can be pretty big.  In the case of e.g. memcached, that's
    # a lot of RAM spent on giant pages that consist half of whitespace.
    # Solution: gzip everything.  Use level 1 for speed!
    def cache_me(context, mako_def):
        c.timer.from_cache = True

        def generate_page():
            c.timer.from_cache = False
            do_work(request, key)
            data = capture(context, mako_def.body).encode('utf8')
            return zlib.compress(data, 1)

        data = content_cache.get_value(key=key, createfunc=generate_page)
        context.write(
            zlib.decompress(data).decode('utf8')
        )

    c._cache_me = cache_me
    return


