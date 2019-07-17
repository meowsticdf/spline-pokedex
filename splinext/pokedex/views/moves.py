# encoding: utf-8

from __future__ import absolute_import, division

from collections import defaultdict, namedtuple

from sqlalchemy.sql import func
from sqlalchemy.orm import (joinedload, joinedload_all, subqueryload, subqueryload_all)
from sqlalchemy.orm.exc import NoResultFound, MultipleResultsFound
import pyramid.httpexceptions as exc

import pokedex.db.tables as t

from .. import db
from .. import helpers
from . import viewlib

# XXX(pyramid): move these to a shared module
from .pokemon import _move_tutor_version_groups, _collapse_pokemon_move_columns, _pokemon_move_method_sort_key

def first(func, iterable):
    """Returns the first element in iterable for which func(elem) is true.

    Equivalent to next(ifilter(func, iterable)).
    """

    for elem in iterable:
        if func(elem):
            return elem

def move_list(request):
    return {}

def move_view(request):
    name = request.matchdict.get('name')
    c = request.tmpl_context

    try:
        c.move = db.get_by_name_query(t.Move, name).one()
    except NoResultFound:
        raise exc.HTTPNotFound()
    except MultipleResultsFound:
        # Bad hack to fix having duplicate moves with the same name
        # (z-moves exist as both physical and special)
        c.move = db.get_by_name_query(t.Move, name).first()

    ### Prev/next for header
    # Shadow moves have the prev/next Shadow move; other moves skip them
    # XXX use identifier
    if c.move.type_id == 10002:
        shadowness = t.Move.type_id == 10002
    else:
        shadowness = t.Move.type_id != 10002

    c.prev_move, c.next_move = helpers.prev_next(
        table=t.Move,
        filters=[shadowness],
        language=c.game_language,
        current=c.move,
    )

    # XXX(pyramid)
    viewlib.cache_content(
        request=request,
        key=c.move.identifier,
        do_work=_do_move,
    )

    return {}

def _do_move(request, cache_key):
    c = request.tmpl_context

    # Eagerload
    db.pokedex_session.query(t.Move) \
        .filter_by(id=c.move.id) \
        .options(
            joinedload('damage_class'),
            joinedload('type'),
            subqueryload('type.damage_efficacies'),
            joinedload('type.damage_efficacies.target_type'),
            joinedload('target'),
            joinedload('move_effect'),
            joinedload_all(t.Move.contest_effect, t.ContestEffect.prose),
            joinedload('contest_type'),
            #joinedload('super_contest_effect'),
            joinedload('move_flags.flag'),
            subqueryload_all('names'),
            joinedload(t.Move.flavor_text, t.MoveFlavorText.version_group),
            joinedload(t.Move.flavor_text, t.MoveFlavorText.version_group, t.VersionGroup.generation),
            joinedload(t.Move.flavor_text, t.MoveFlavorText.version_group, t.VersionGroup.versions),
            joinedload('contest_combo_first.second'),
            joinedload('contest_combo_second.first'),
            joinedload('super_contest_combo_first.second'),
            joinedload('super_contest_combo_second.first'),
        ) \
        .one()

    # Used for item linkage
    c.pp_up = db.pokedex_session.query(t.Item) \
        .filter_by(identifier=u'pp-up').one()

    ### Power percentile
    if c.move.power is None:
        c.power_percentile = None
    else:
        q = db.pokedex_session.query(t.Move) \
            .filter(t.Move.power.isnot(None))
        less = q.filter(t.Move.power < c.move.power).count()
        equal = q.filter(t.Move.power == c.move.power).count()
        c.power_percentile = (less + equal * 0.5) / q.count()

    ### Flags
    c.flags = []
    move_flags = db.pokedex_session.query(t.MoveFlag) \
                                .order_by(t.MoveFlag.id.asc())
    for flag in move_flags:
        has_flag = flag in c.move.flags
        c.flags.append((flag, has_flag))

    ### Machines
    q = db.pokedex_session.query(t.Generation) \
        .filter(t.Generation.id >= c.move.generation.id) \
        .options(
            joinedload('version_groups'),
        ) \
        .order_by(t.Generation.id.asc())
    raw_machines = {}
    # raw_machines = { generation: { version_group: machine_number } }
    c.machines = {}
    # c.machines: generation => [ (versions, machine_number), ... ]
    # Populate an empty dict first so we know which versions don't have a
    # TM for this move
    for generation in q:
        c.machines[generation] = []
        raw_machines[generation] = {}
        for version_group in generation.version_groups:
            raw_machines[generation][version_group] = None

    # Fetch the actual machine numbers
    for machine in c.move.machines:
        raw_machines[machine.version_group.generation] \
                    [machine.version_group] = machine.machine_number

    # Collapse that into an easily-displayed form
    VersionMachine = namedtuple('VersionMachine',
                                ['version_group', 'machine_number'])
    # dictionary -> list of tuples
    for generation, vg_numbers in raw_machines.items():
        for version_group, machine_number in vg_numbers.items():
            c.machines[generation].append(
                VersionMachine(version_group=version_group,
                                machine_number=machine_number,
                )
            )
    for generation, vg_numbers in c.machines.items():
        machine_numbers = [_.machine_number for _ in vg_numbers]
        if len(set(machine_numbers)) == 1:
            # Merge generations that have the same machine number everywhere
            c.machines[generation] = [( None, vg_numbers[0].machine_number )]
        else:
            # Otherwise, sort by version group
            vg_numbers.sort(key=lambda item: item.version_group.id)

    ### Similar moves
    c.similar_moves = db.pokedex_session.query(t.Move) \
        .join(t.Move.move_effect) \
        .filter(t.MoveEffect.id == c.move.effect_id) \
        .filter(t.Move.id != c.move.id) \
        .options(joinedload('type')) \
        .all()

    ### Pokémon
    # This is kinda like the moves for Pokémon, but backwards.  Imagine
    # that!  We have the same basic structure, a list of:
    #     (method, [ (pokemon, { version_group => data, ... }), ... ])
    pokemon_methods = defaultdict(dict)
    # Sort by descending level because the LAST level seen is the one that
    # ends up in the table, and the lowest level is the most useful
    q = db.pokedex_session.query(t.PokemonMove) \
        .options(
            joinedload('method'),
            joinedload('pokemon'),
            joinedload('version_group'),
            joinedload('pokemon.species'),
            joinedload('pokemon.stats.stat'),
            joinedload('pokemon.stats.stat.damage_class'),
            joinedload('pokemon.default_form'),

            # Pokémon table stuff
            subqueryload('pokemon.abilities'),
            subqueryload('pokemon.hidden_ability'),
            subqueryload('pokemon.species'),
            subqueryload('pokemon.species.egg_groups'),
            subqueryload('pokemon.stats'),
            subqueryload('pokemon.types'),
        ) \
        .filter(t.PokemonMove.move_id == c.move.id) \
        .order_by(t.PokemonMove.level.desc())
    for pokemon_move in q:
        method_list = pokemon_methods[pokemon_move.method]
        this_vg = pokemon_move.version_group

        # Create a container for data for this method and version(s)
        vg_data = dict()

        if pokemon_move.method.identifier == u'level-up':
            # Level-ups need to know what level
            vg_data['level'] = pokemon_move.level
        elif pokemon_move.method.identifier == u'machine':
            # TMs need to know their own TM number
            machine = first(lambda _: _.version_group == this_vg,
                            c.move.machines)
            if machine:
                vg_data['machine'] = machine.machine_number

        # The Pokémon version does sorting here, but we're just going to
        # sort by name regardless of method, so leave that until last

        # Add in the move method for this Pokémon
        if pokemon_move.pokemon not in method_list:
            method_list[pokemon_move.pokemon] = dict()

        method_list[pokemon_move.pokemon][this_vg] = vg_data

    # Convert each method dictionary to a list of tuples
    c.better_damage_classes = {}
    for method in pokemon_methods.keys():
        # Also grab Pokémon's better damage classes
        for pokemon in pokemon_methods[method].keys():
            if pokemon not in c.better_damage_classes:
                c.better_damage_classes[pokemon] = \
                    pokemon.better_damage_class

        pokemon_methods[method] = pokemon_methods[method].items()

    # Convert the entire dictionary to a list of tuples and sort it
    c.pokemon = pokemon_methods.items()
    c.pokemon.sort(key=_pokemon_move_method_sort_key)

    for method, method_list in c.pokemon:
        # Sort each method's rows by their Pokémon
        method_list.sort(key=lambda row: row[0].order)

    # Finally, collapse identical columns within the same generation
    c.pokemon_columns \
        = _collapse_pokemon_move_columns(table=c.pokemon, thing=c.move)

    # Grab list of all the version groups with tutor moves
    c.move_tutor_version_groups = _move_tutor_version_groups(c.pokemon)

    # Total number of Pokémon that learn this move
    c.pokemon_count = db.pokedex_session.query(t.Pokemon).filter(
        t.Pokemon.id.in_(
            db.pokedex_session.query(t.PokemonMove.pokemon_id)
                .filter_by(move_id=c.move.id)
                .subquery()
        )
    ).value(func.count(t.Pokemon.id))
