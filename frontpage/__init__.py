from collections import defaultdict
import re

from .sources import FeedSource, GitSource

source_types = {
    'rss': FeedSource,
    'git': GitSource,
}

def load_sources_hook(config, *args, **kwargs):
    """Hook to load all the known sources and stuff them in config.  Run once,
    on server startup.

    Frontpage hooks are also passed the `config` hash, as it's not available
    during setup.
    """
    # Extract source definitions from config and store as source_name => config
    update_config = defaultdict(dict)
    key_rx = re.compile(
        '(?x) ^ spline-frontpage [.] sources [.] (\w+) (?: [.] (\w+) )? $')
    for key, val in config.iteritems():
        # Match against spline-frontpage.source.(source).(key)
        match = key_rx.match(key)
        if not match:
            continue

        source_name, subkey = match.groups()
        if not subkey:
            # This is the type declaration; use a special key
            subkey = '__type__'

        update_config[source_name][subkey] = val

    # Figure out the global limit and expiration time, with reasonable
    # defaults.  Make sure they're integers.
    global_limit = int(config.get('spline-frontpage.limit', 10))
    # max_age is optional and can be None
    try:
        global_max_age = int(config['spline-frontpage.max_age'])
    except KeyError:
        global_max_age = None

    config['spline-frontpage.limit'] = global_limit
    config['spline-frontpage.max_age'] = global_max_age

    # Ask plugins to turn configuration into source objects
    sources = []
    for source, source_config in update_config.iteritems():
        source_type = source_types[source_config['__type__']]
        del source_config['__type__']  # don't feed this to constructor!

        # Default to global limit and max age.  Source takes care of making
        # integers and whatnot
        source_config.setdefault('limit', global_limit)
        source_config.setdefault('max_age', global_max_age)

        # Hooks return a list of sources; combine with running list
        sources += [source_type(config=config, **source_config)]

    # Save the list of sources, and done
    config['spline-frontpage.sources'] = sources

def source_cron_hook(*args, **kwargs):
    """Hook to pass on cron tics to all sources, should they need it for e.g.
    caching.
    """
    for source in config['spline-frontpage.sources']:
        source.do_cron(*args, **kwargs)
