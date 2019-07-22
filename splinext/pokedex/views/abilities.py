# encoding: utf-8

import re

from sqlalchemy.orm import (joinedload, joinedload_all, subqueryload, subqueryload_all)
from sqlalchemy.orm.exc import NoResultFound
import pyramid.httpexceptions as exc

import pokedex.db.tables as t

from .. import db
from .. import helpers
from . import viewlib

def ability_list(request):
    c = request.tmpl_context

    c.abilities = db.pokedex_session.query(t.Ability) \
        .join(t.Ability.names_local) \
        .filter(t.Ability.is_main_series) \
        .options(joinedload('prose.short_effect')) \
        .order_by(t.Ability.generation_id.asc(),
            t.Ability.names_table.name.asc()) \
        .all()

    return {}

def ability_view(request):
    name = request.matchdict.get('name')
    c = request.tmpl_context

    try:
        # Make sure that any ability we get is from the main series
        c.ability = (db.get_by_name_query(t.Ability, name)
            .filter(t.Ability.is_main_series)
            .one())
    except NoResultFound:
        raise exc.HTTPNotFound

    ### Prev/next for header
    c.prev_ability, c.next_ability = helpers.prev_next(
        table=t.Ability,
        current=c.ability,
        language=c.game_language,
        filters=[t.Ability.is_main_series],
    )

    viewlib.cache_content(
        request=request,
        key=c.ability.identifier,
        do_work=_do_ability,
    )

    return {}

def _do_ability(request, cache_key):
    c = request.tmpl_context

    # Eagerload
    db.pokedex_session.query(t.Ability) \
        .filter_by(id=c.ability.id) \
        .options(
            joinedload(t.Ability.names_local),

            subqueryload(t.Ability.flavor_text),
            joinedload(t.Ability.flavor_text, t.AbilityFlavorText.version_group),
            joinedload(t.Ability.flavor_text, t.AbilityFlavorText.version_group, t.VersionGroup.versions),

            # Pokémon stuff
            subqueryload(t.Ability.pokemon),
            subqueryload(t.Ability.hidden_pokemon),
            subqueryload(t.Ability.all_pokemon),
            subqueryload(t.Ability.all_pokemon, t.Pokemon.abilities),
            subqueryload(t.Ability.all_pokemon, t.Pokemon.species, t.PokemonSpecies.egg_groups),
            subqueryload(t.Ability.all_pokemon, t.Pokemon.types),
            subqueryload(t.Ability.all_pokemon, t.Pokemon.stats),
            joinedload(t.Ability.all_pokemon, t.Pokemon.stats, t.PokemonStat.stat),
        ) \
        .one()

    c.method_labels = {
        'Normal': u'May be found normally on Pokémon.',
        'Hidden': u'Found on Pokémon from the Dream World and Dream Radar, '
                  u'as well as a few Pokémon from specific in-game encounters.',
    }

    hidden_pokemon = [pokemon for pokemon in c.ability.hidden_pokemon if
                      pokemon not in c.ability.pokemon]

    c.pokemon = []
    if c.ability.pokemon:
        c.pokemon.append(('Normal', c.ability.pokemon))
    if hidden_pokemon:
        c.pokemon.append(('Hidden', hidden_pokemon))

    move_flag = None
    if c.ability.identifier == u'soundproof':
        move_flag = 'sound'
    elif c.ability.identifier == u'iron-fist':
        move_flag = 'punch'

    c.moves = []
    if move_flag:
        c.moves = db.pokedex_session.query(t.Move) \
            .join(t.MoveFlagMap, t.MoveFlag) \
            .filter(t.MoveFlag.identifier == move_flag) \
            .join(t.Move.names_local) \
            .order_by(t.Move.names_table.name) \
            .options(
                subqueryload('move_effect'),
                subqueryload('type'),
                subqueryload('damage_class')
            ) \
            .all()
