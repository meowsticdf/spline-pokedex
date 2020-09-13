# encoding: utf8
"""Collection of small functions and scraps of data that don't belong in the
pokedex core -- either because they're inherently Web-related, or because
they're very flavorful and don't belong or fit well in a database.
"""

from __future__ import absolute_import, division

import math
import re
from itertools import groupby, chain, repeat
from operator import attrgetter
import os.path

import pokedex.db.tables as t
from . import db
from . import splinehelpers as h
from .i18n import NullTranslator

# Re-exported
import pokedex.formulae as formulae
from pokedex.roomaji import romanize

# We can't translate at import time, but _ will mark strings as translatable
# Functions that need translation will take a "_" parameter, which defaults
# to this:
_ = NullTranslator()

def resource_url(request, thingy, subpage=None, controller='dex'):
    u"""Given a thingy (Pokémon, move, type, whatever), returns a URL to it.
    """
    # Using the table name as an action directly looks kinda gross, but I can't
    # think of anywhere I've ever broken this convention, and making a
    # dictionary to get data I already have is just silly
    args = {}

    # Pokémon with forms need the form attached to the URL
    if isinstance(thingy, t.PokemonForm):
        action = 'pokemon'
        args.setdefault('_query', {})
        args['_query']['form'] = thingy.form_identifier.lower()
        args['name'] = thingy.pokemon.species.name.lower()

        if not thingy.is_default:
            subpage = 'flavor'
    elif isinstance(thingy, t.PokemonSpecies):
        action = 'pokemon'
        args['name'] = thingy.name.lower()
    else:
        action = thingy.__tablename__
        args['name'] = thingy.name.lower()


    # Items are split up by pocket
    if isinstance(thingy, t.Item):
        args['pocket'] = thingy.pocket.identifier

    if (thingy.__tablename__.startswith('conquest_')
       or (isinstance(thingy, t.Ability) and not thingy.is_main_series)
       or subpage == 'conquest'):
        # Conquest stuff needs to go to the Conquest controller
        if action == 'conquest_warrior_skills':
            action = 'skills'
        else:
            action = action.replace('conquest_', '')

        controller = 'dex_conquest'
    elif subpage:
        action += '_' + subpage

    route = controller + "/" + action
    return request.route_url(route, **args)

def render_flavor_text(flavor_text, literal=False):
    """Makes flavor text suitable for HTML presentation.

    If `literal` is false, collapses broken lines into single lines.

    If `literal` is true, linebreaks are preserved exactly as they are in the
    games.
    """

    # n.b.: \u00ad is soft hyphen

    # Somehow, the games occasionally have \n\f, which makes no sense at all
    # and wouldn't render in-game anyway.  Fix this
    flavor_text = flavor_text.replace('\n\f', '\f')

    if literal:
        # Page breaks become two linebreaks.
        # Soft hyphens become real hyphens.
        # Newlines become linebreaks.
        html = flavor_text.replace(u'\f',       u'<br><br>') \
                          .replace(u'\u00ad',   u'-') \
                          .replace(u'\n',       u'<br>')

    else:
        # Page breaks are treated just like newlines.
        # Soft hyphens followed by newlines vanish.
        # Letter-hyphen-newline becomes letter-hyphen, to preserve real
        # hyphenation.
        # Any other newline becomes a space.
        html = flavor_text.replace(u'\f',       u'\n') \
                          .replace(u'\u00ad\n', u'') \
                          .replace(u'\u00ad',   u'') \
                          .replace(u' -\n',     u' - ') \
                          .replace(u'-\n',      u'-') \
                          .replace(u'\n',       u' ')

        # Collapse adjacent spaces and strip trailing whitespace.
        html = u' '.join(html.split())

    return h.literal(html)

## Collapsing

def collapse_flavor_text_key(literal=True):
    """A wrapper around `render_flavor_text`. Returns a function to be used
    as a key for `collapse_versions`, or any other function which takes a key.
    """
    def key(text):
        return render_flavor_text(text.flavor_text, literal=literal)
    return key

def group_by_generation(things):
    """A wrapper around itertools.groupby which groups by generation."""
    things = iter(things)
    try:
        a_thing = things.next()
    except StopIteration:
        return ()
    key = get_generation_key(a_thing)
    return groupby(chain([a_thing], things), key)

def get_generation_key(sample_object):
    """Given an object, return a function which retrieves the generation.

    Tries x.generation, x.version_group.generation, and x.version.generation.
    """
    if hasattr(sample_object, 'generation'):
        return attrgetter('generation')
    elif hasattr(sample_object, 'version_group'):
        return (lambda x: x.version_group.generation)
    elif hasattr(sample_object, 'version'):
        return (lambda x: x.version.generation)
    raise AttributeError

def collapse_versions(things, key):
    """Collapse adjacent equal objects and remember their versions.

    Yields tuples of ([versions], key(x)). Uses itertools.groupby internally.
    """
    things = iter(things)
    # let the StopIteration bubble up
    a_thing = things.next()

    if hasattr(a_thing, 'version'):
        def get_versions(things):
            return [x.version for x in things]
    elif hasattr(a_thing, 'version_group'):
        def get_versions(things):
            return sum((x.version_group.versions for x in things), [])

    for collapsed_key, group in groupby(chain([a_thing], things), key):
        yield get_versions(group), collapsed_key

### Filenames

# XXX only used by version_icons()
def filename_from_name(name):
    """Shorten the name of a whatever to something suitable as a filename.

    e.g. Water's Edge -> waters-edge
    """
    name = name.lower()

    name = re.sub(u'[ _]+', u'-', name)
    name = re.sub(u'[\'.()]', u'', name)
    return name

def pokemon_has_media(pokemon_form, prefix, ext, config, use_form=True):
    """Determine whether a file exists in the specified directory for the
    specified Pokémon form.
    """
    # TODO share this somewhere
    media_dir = config.get('spline-pokedex.media_directory', None)
    if not media_dir:
        return False

    if use_form:
        kwargs = dict(form=pokemon_form)
    else:
        kwargs = dict()

    return os.path.exists(os.path.join(media_dir,
        pokemon_media_path(pokemon_form.species, prefix, ext, **kwargs)))

def pokemon_media_path(pokemon_species, prefix, ext, form=None):
    """Returns a path to a Pokémon media file.

    form is not None if the form should be in the filename; it should be False
    if the form should be ignored, e.g. for footprints.
    """

    if form:
        form_identifier = form.form_identifier
    else:
        form_identifier = None

    if form_identifier:
        filename = '{id}-{form}.{ext}'
    else:
        filename = '{id}.{ext}'

    filename = filename.format(
        id=pokemon_species.id,
        form=form_identifier,
        ext=ext
    )

    return '/'.join(('pokemon', prefix, filename))

def item_filename(item):
    if item.pocket.identifier == u'machines':
        machines = item.machines
        prefix = u'hm' if machines[-1].is_hm else u'tm'
        filename = prefix + u'-' + machines[-1].move.type.identifier
    elif item.identifier.startswith(u'data-card-'):
        filename = u'data-card'
    else:
        filename = item.identifier

    return filename

def joiner(sep):
    """Returns an iterator which yields sep every time except the first.

    Useful for printing out a comma-separated list.
    """
    return chain([u''], repeat(sep))


### Labels

# Type efficacy, from percents to Unicode fractions
type_efficacy_label = {
    0: '0',
    25: u'¼',
    50: u'½',
    100: '1',
    200: '2',
    400: '4',
}

# Gender rates, translated from -1..8 to useful text
gender_rate_label = {
    -1: _(u'genderless'),
    0: _(u'always male'),
    1: _(u'⅞ male, ⅛ female'),
    2: _(u'¾ male, ¼ female'),
    3: _(u'⅝ male, ⅜ female'),
    4: _(u'½ male, ½ female'),
    5: _(u'⅜ male, ⅝ female'),
    6: _(u'¼ male, ¾ female'),
    7: _(u'⅛ male, ⅞ female'),
    8: _(u'always female'),
}

conquest_rank_label = {
    1: 'I',
    2: 'II',
    3: 'III'
}

def article(noun, _=_):
    """Returns 'a' or 'an', as appropriate."""
    if noun[0].lower() in u'aeiou':
        return _(u'an')
    return _(u'a')


### Formatting

# Attempts at reasonable defaults for trainer size, based on the average
# American
trainer_height = 17.8  # dm
trainer_weight = 780   # hg

def format_height_metric(height):
    """Formats a height in decimeters as M m."""
    return "%.1f m" % (height / 10)

def format_height_imperial(height):
    """Formats a height in decimeters as F'I"."""
    return "%d'%.1f\"" % (
        height * 0.32808399,
        (height * 0.32808399 % 1) * 12,
    )

def format_weight_metric(weight):
    """Formats a weight in hectograms as K kg."""
    return "%.1f kg" % (weight / 10)

def format_weight_imperial(weight):
    """Formats a weight in hectograms as L lb."""
    return "%.1f lb" % (weight / 10 * 2.20462262)


### General data munging

def scale_sizes(size_dict, dimensions=1):
    """Normalizes a list of sizes so the largest is 1.0.

    Use `dimensions` if the sizes are non-linear, i.e. 2 for scaling area.
    """

    # x -> (x/max)^(1/dimensions)
    max_size = float(max(size_dict.values()))
    scaled_sizes = dict()
    for k, v in size_dict.items():
        scaled_sizes[k] = math.pow(v / max_size, 1.0 / dimensions)
    return scaled_sizes


def _no_icon(pokemon):
    return u""

def apply_pokemon_template(template, pokemon, get_icon=_no_icon, _=_):
    u"""`template` should be a string.Template object.

    Uses safe_substitute to inject some fields from the Pokémon into the
    template.

    This cheerfully returns a literal, so be sure to escape the original format
    string BEFORE passing it to Template!
    """

    d = dict(
        icon=get_icon(pokemon),
        id=pokemon.species.id,
        name=pokemon.default_form.name,

        height=format_height_imperial(pokemon.height),
        height_ft=format_height_imperial(pokemon.height),
        height_m=format_height_metric(pokemon.height),
        weight=format_weight_imperial(pokemon.weight),
        weight_lb=format_weight_imperial(pokemon.weight),
        weight_kg=format_weight_metric(pokemon.weight),

        gender=_(gender_rate_label[pokemon.species.gender_rate]),
        genus=pokemon.species.genus,
        base_experience=pokemon.base_experience,
        capture_rate=pokemon.species.capture_rate,
        base_happiness=pokemon.species.base_happiness,
    )

    # "Lazy" loading, to avoid hitting other tables if unnecessary.  This is
    # very chumpy and doesn't distinguish between literal text and fields (e.g.
    # '$type' vs 'type'), but that's very unlikely to happen, and it's not a
    # big deal if it does
    if 'type' in template.template:
        types = pokemon.types
        d['type'] = u'/'.join(type_.name for type_ in types)
        d['type1'] = types[0].name
        d['type2'] = types[1].name if len(types) > 1 else u''

    if 'egg_group' in template.template:
        egg_groups = pokemon.species.egg_groups
        d['egg_group'] = u'/'.join(group.name for group in egg_groups)
        d['egg_group1'] = egg_groups[0].name
        d['egg_group2'] = egg_groups[1].name if len(egg_groups) > 1 else u''

    if 'ability' in template.template:
        abilities = pokemon.abilities
        d['ability'] = u'/'.join(ability.name for ability in abilities)
        d['ability1'] = abilities[0].name
        d['ability2'] = abilities[1].name if len(abilities) > 1 else u''
        if pokemon.hidden_ability:
            d['hidden_ability'] = pokemon.hidden_ability.name
        else:
            d['hidden_ability'] = u''

    if 'color' in template.template:
        d['color'] = pokemon.species.color.name

    if 'habitat' in template.template:
        if pokemon.species.habitat:
            d['habitat'] = pokemon.species.habitat.name
        else:
            d['habitat'] = ''

    if 'shape' in template.template:
        if pokemon.species.shape:
            d['shape'] = pokemon.species.shape.name
        else:
            d['shape'] = ''

    if 'hatch_counter' in template.template:
        d['hatch_counter'] = pokemon.species.hatch_counter

    if 'steps_to_hatch' in template.template:
        d['steps_to_hatch'] = (pokemon.species.hatch_counter + 1) * 255

    if 'stat' in template.template or \
       'hp' in template.template or \
       'attack' in template.template or \
       'defense' in template.template or \
       'speed' in template.template or \
       'effort' in template.template:
        d['effort'] = u', '.join("{0} {1}".format(_.effort, _.stat.name)
                                 for _ in pokemon.stats if _.effort)

        d['stats'] = u'/'.join(str(_.base_stat) for _ in pokemon.stats)

        for pokemon_stat in pokemon.stats:
            key = pokemon_stat.stat.name.lower().replace(' ', '_')
            d[key] = pokemon_stat.base_stat

    return h.literal(template.safe_substitute(d))

def apply_move_template(template, move):
    u"""`template` should be a string.Template object.

    Uses safe_substitute to inject some fields from the move into the template,
    just like the above.
    """

    d = dict(
        id=move.id,
        name=move.name,
        type=move.type.name,
        damage_class=move.damage_class.name,
        pp=move.pp,
        power=move.power,
        accuracy=move.accuracy,

        priority=move.priority,
        effect_chance=move.effect_chance,
        effect=move.move_effect.short_effect,
    )

    return h.literal(template.safe_substitute(d))


class DownloadSizer(object):
    file_size_units = 'B KB MB GB TB'.split()

    def __init__(self):
        self.seen = set()

    def compute(self, path):
        # XXX The exceptions raised below should be warnings instead.
        # I assert that it is better to have a couple broken links than
        # for the page to completely crash.
        if path in self.seen:
            # Two download links for the same thing on one page
            # Remove the "seen" stuff if this is ever legitimate
            raise AssertionError('Copy/paste oversight! Two equal download links on one page')
        self.seen.add(path)
        root, me = os.path.split(__file__)
        path = os.path.join(root, 'public', path)
        try:
            size = os.stat(path).st_size
        except EnvironmentError:
            raise EnvironmentError("Could not stat %s. Make sure to run spline-pokedex's bin/create-downloads.py script." % path)
        def str_no_trailing_zero(num):
            s = str(num)
            if s.endswith('.0'):
                s = s[:-2]
            return s
        for unit in self.file_size_units:
            if size < 1024:
                if size >= 100:
                    return str(int(round(size))) + unit
                elif size >= 10:
                    return str_no_trailing_zero(round(size, 1)) + unit
                else:
                    return str_no_trailing_zero(round(size, 2)) + unit
            else:
                size = size / 1024.
        else:
            raise AssertionError('Serving a file of %s petabytes', size)
