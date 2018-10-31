# encoding: utf-8

from collections import defaultdict
import re

from sqlalchemy.orm import (joinedload, joinedload_all, subqueryload, subqueryload_all)
from sqlalchemy.orm.exc import NoResultFound
import pyramid.httpexceptions as exc

import pokedex.db.tables as t

from .. import db

# Dict of method identifier => icon path
encounter_method_icons = {
    'walk': 'grass.png',
    'dark-grass': 'dark-grass.png',

    'surf': 'water.png',

    'old-rod': 'old-rod.png',
    'good-rod': 'good-rod.png',
    'super-rod': 'super-rod.png',

    'rock-smash': 'rock-smash.png',

    # We don't have an icon for rustling grass, so just use the grass icon.
    # We don't have an icon for fishing in water spots, so just use the
    # water spot icon.
    'grass-spots': 'grass.png',
    'cave-spots': 'cave-spots.png',
    'bridge-spots': 'bridge-spots.png',
    'surf-spots': 'water-spots.png',
    'super-rod-spots': 'water-spots.png',

    'gift': 'gift.png',
    'gift-egg': 'egg.png',
}

# Maps condition value identifiers to representative icons
encounter_condition_value_icons = {
    'swarm-no': 'swarm-no.png',
    'swarm-yes': 'swarm-yes.png',
    'time-morning': 'time-morning.png',
    'time-day': 'time-daytime.png',
    'time-night': 'time-night.png',
    'radar-off': 'pokeradar-off.png',
    'radar-on': 'pokeradar-on.png',
    'slot2-none': 'slot2-none.png',
    'slot2-ruby': 'slot2-ruby.png',
    'slot2-sapphire': 'slot2-sapphire.png',
    'slot2-emerald': 'slot2-emerald.png',
    'slot2-firered': 'slot2-firered.png',
    'slot2-leafgreen': 'slot2-leafgreen.png',
    'radio-off': 'radio-off.png',
    'radio-hoenn': 'radio-hoenn.png',
    'radio-sinnoh': 'radio-sinnoh.png',
    'season-spring': 'season-spring.png',
    'season-summer': 'season-summer.png',
    'season-autumn': 'season-autumn.png',
    'season-winter': 'season-winter.png',
}

def level_range(a, b):
    """If a and b are the same, returns 'L{a}'.  Otherwise, returns 'L{a}–{b}'.
    """

    if a == b:
        return u"L{0}".format(a)
    else:
        return u"L{0}–{1}".format(a, b)

def location_list(request):
    c = request.tmpl_context

    c.locations = (db.pokedex_session.query(t.Location)
        .join(t.Location.names_local)
        .join(t.LocationArea, t.Encounter)
        .order_by(t.Location.region_id, t.Location.names_table.name)
        .all()
    )

    return {}

def location_view(request):
    name = request.matchdict.get('name')
    c = request.tmpl_context

    # Note that it isn't against the rules for multiple locations to have
    # the same name.  To avoid complications, the name is stored in
    # c.location_name, and after that we only deal with areas.
    c.locations = db.get_by_name_query(t.Location, name).all()

    if not c.locations:
        raise exc.NotFound()

    c.location_name = c.locations[0].name

    # TODO: Stick the region in the url; e.g. locations/kanto/route 1

    c.region_areas = defaultdict(list)

    # Get all the areas in any of these locations
    for location in c.locations:
        if location.areas:
            c.region_areas[location.region].extend(location.areas)

    # For the most part, our data represents exactly what we're going to
    # show.  For a given area in a given game, this Pokémon is guaranteed
    # to appear some x% of the time no matter what the state of the world
    # is, and various things like swarms or the radar may add on to this
    # percentage.

    # Encounters are grouped by area -- <h2>s.
    # Then by method -- table sections.
    # Then by pokemon -- table rows.
    # Then by version -- table columns.
    # Finally, condition values associated with levels/rarity.
    q = db.pokedex_session.query(t.Encounter) \
        .options(
            joinedload_all('condition_values'),
            joinedload_all('slot.method'),
            joinedload_all('pokemon.species'),
            joinedload('version'),
        ) \
        .filter(t.Encounter.location_area_id.in_(
            x.id for areas in c.region_areas.values() for x in areas
        ))

    # area => method => pokemon => version => condition =>
    #     condition_values => encounter_bits
    grouped_encounters = defaultdict(
        lambda: defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(
                    lambda: defaultdict(
                        lambda: defaultdict(
                            list
                        )
                    )
                )
            )
        )
    )

    # To avoid an ultra-wide table when not necessary, only *generations*
    # that actually contain this Pokémon should appear.
    # So if the Pokémon appears in Kanto in Crystal, show all of G/S/C.  If
    # it doesn't appear in any of the three, show none of them.
    # Last but not least, show generations in reverse order, so the more
    # important (i.e., recent) versions are on the left.
    # Got all that?
    area_generations = defaultdict(set)

    for encounter in q.all():
        # Fetches the list of encounters that match this region, version,
        # method, etc.

        # n.b.: conditions and values must be tuples because lists aren't
        # hashable.
        encounter_bits = grouped_encounters \
            [encounter.location_area] \
            [encounter.slot.method] \
            [encounter.pokemon] \
            [encounter.version] \
            [ tuple(cv.condition for cv in encounter.condition_values) ] \
            [ tuple(encounter.condition_values) ]

        # Combine "level 3-4, 50%" and "level 3-4, 20%" into "level 3-4, 70%".
        existing_encounter = filter(lambda enc: enc['min_level'] == encounter.min_level
                                            and enc['max_level'] == encounter.max_level,
                                    encounter_bits)
        if existing_encounter:
            existing_encounter[0]['rarity'] += encounter.slot.rarity
        else:
            encounter_bits.append({
                'min_level': encounter.min_level,
                'max_level': encounter.max_level,
                'rarity': encounter.slot.rarity,
            })

        # Remember that this generation appears in this area
        area_generations[encounter.location_area].add(encounter.version.version_group.generation)

    c.grouped_encounters = grouped_encounters

    # Pass some data/functions
    c.encounter_method_icons = encounter_method_icons
    c.encounter_condition_value_icons = encounter_condition_value_icons
    c.level_range = level_range

    # See above.  Versions for each major group are those that are part of
    # a generation where this Pokémon appears -- in reverse generation
    # order.
    c.group_versions = defaultdict(list)
    for area, generations in area_generations.items():
        for version_group in area.location.region.version_groups:
            if version_group.generation not in generations:
                continue
            c.group_versions[area][0:0] = version_group.versions

    return {}
