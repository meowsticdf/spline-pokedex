# encoding: utf-8

import re

from sqlalchemy import func
from sqlalchemy.orm import contains_eager, aliased
from sqlalchemy.orm import (joinedload, joinedload_all, subqueryload, subqueryload_all)
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import (and_, or_)
import pyramid.httpexceptions as exc

import pokedex.db.tables as t

from .. import db
from .. import helpers

def natures_list(request):
    c = request.tmpl_context

    c.natures = db.pokedex_session.query(t.Nature) \
        .join(t.Nature.names_local) \
        .options(
            contains_eager(t.Nature.names_local),
            joinedload(t.Nature.likes_flavor),
            joinedload(t.Nature.hates_flavor),
            joinedload(t.Nature.increased_stat),
            joinedload(t.Nature.decreased_stat),
        )

    # Figure out sort order
    c.sort_order = request.params.get('sort', None)
    if c.sort_order == u'stat':
        # Sort neutral natures first, sorted by name, then the others in
        # stat order
        c.natures = c.natures.order_by(
            (t.Nature.increased_stat_id
                == t.Nature.decreased_stat_id).desc(),
            t.Nature.increased_stat_id.asc(),
            t.Nature.decreased_stat_id.asc(),
        )
    else:
        c.natures = c.natures.order_by(
            t.Nature.names_table.name.asc())

    characteristic_table = dict()
    characteristics = (
        db.pokedex_session.query(t.Characteristic)
        .options(joinedload(t.Characteristic.text_local))
    )

    for characteristic in characteristics:
        subdict = characteristic_table.setdefault(characteristic.stat, {})
        subdict[characteristic.gene_mod_5] = characteristic.message

    c.characteristics = characteristic_table

    return {}

def nature_view(request):
    name = request.matchdict.get('name')
    c = request.tmpl_context

    try:
        c.nature = db.get_by_name_query(t.Nature, name).one()
    except NoResultFound:
        raise exc.HTTPNotFound()

    ### Prev/next for header
    c.prev_nature, c.next_nature = helpers.prev_next(
        table=t.Nature,
        current=c.nature,
        language=c.game_language,
    )

    # Find related natures.
    # Other neutral natures if this one is neutral; otherwise, the inverse
    # of this one
    if c.nature.increased_stat == c.nature.decreased_stat:
        c.neutral_natures = db.pokedex_session.query(t.Nature) \
            .join(t.Nature.names_local) \
            .filter(t.Nature.increased_stat_id
                    == t.Nature.decreased_stat_id) \
            .filter(t.Nature.id != c.nature.id) \
            .order_by(t.Nature.names_table.name)
    else:
        c.inverse_nature = db.pokedex_session.query(t.Nature) \
            .filter_by(
                increased_stat_id=c.nature.decreased_stat_id,
                decreased_stat_id=c.nature.increased_stat_id,
            ) \
            .one()

    # Find appropriate example Pokémon.
    # Arbitrarily decided that these are Pokémon for which:
    # - their best and worst stats are at least 10 apart
    # - their best stat is improved by this nature
    # - their worst stat is hindered by this nature
    # Of course, if this is a neutral nature, then find only Pokémon for
    # which the best and worst stats are close together.
    # The useful thing here is that this cannot be done in the Pokémon
    # search, as it requires comparing a Pokémon's stats to themselves.
    # Also, HP doesn't count.  Durp.
    hp = db.pokedex_session.query(t.Stat).filter_by(identifier=u'hp').one()
    if c.nature.increased_stat == c.nature.decreased_stat:
        # Neutral.  Boring!
        # Create a subquery of neutral-ish Pokémon
        stat_subquery = db.pokedex_session.query(
                t.PokemonStat.pokemon_id
            ) \
            .filter(t.PokemonStat.stat_id != hp.id) \
            .group_by(t.PokemonStat.pokemon_id) \
            .having(
                func.max(t.PokemonStat.base_stat)
                - func.min(t.PokemonStat.base_stat)
                <= 10
            ) \
            .subquery()

        query = db.pokedex_session.query(t.Pokemon) \
            .join((stat_subquery,
                stat_subquery.c.pokemon_id == t.Pokemon.id)) \
            .order_by(t.Pokemon.order)

    else:
        # More interesting.
        # Create the subquery again, but..  the other way around.
        grouped_stats = aliased(t.PokemonStat)
        stat_range_subquery = db.pokedex_session.query(
                grouped_stats.pokemon_id,
                func.max(grouped_stats.base_stat).label('max_stat'),
                func.min(grouped_stats.base_stat).label('min_stat'),
            ) \
            .filter(grouped_stats.stat_id != hp.id) \
            .group_by(grouped_stats.pokemon_id) \
            .having(
                func.max(grouped_stats.base_stat)
                - func.min(grouped_stats.base_stat)
                > 10
            ) \
            .subquery()

        # Also need to join twice more to PokemonStat to figure out WHICH
        # of those stats is the max or min.  So, yes, joining to the same
        # table three times and two deep.  One to make sure the Pokémon has
        # the right lowest stat; one to make sure it has the right highest
        # stat.
        # Note that I really want to do: range --> min; --> max
        # But SQLAlchemy won't let me start from a subquery like that, so
        # instead I do min --> range --> max.  :(  Whatever.
        min_stats = aliased(t.PokemonStat)
        max_stats = aliased(t.PokemonStat)
        minmax_stat_subquery = db.pokedex_session.query(
                min_stats
            ) \
            .join((stat_range_subquery, and_(
                    min_stats.base_stat == stat_range_subquery.c.min_stat,
                    min_stats.pokemon_id == stat_range_subquery.c.pokemon_id,
                )
            )) \
            .join((max_stats, and_(
                    max_stats.base_stat == stat_range_subquery.c.max_stat,
                    max_stats.pokemon_id == stat_range_subquery.c.pokemon_id,
                )
            )) \
            .filter(min_stats.stat_id == c.nature.decreased_stat_id) \
            .filter(max_stats.stat_id == c.nature.increased_stat_id) \
            .subquery()

        # Finally, just join that mess to pokemon; INNER-ness will do all
        # the filtering
        query = db.pokedex_session.query(t.Pokemon) \
            .join((minmax_stat_subquery,
                minmax_stat_subquery.c.pokemon_id == t.Pokemon.id)) \
            .order_by(t.Pokemon.order)

    c.pokemon = query.all()

    return {}
