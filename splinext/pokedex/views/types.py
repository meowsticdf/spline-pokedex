# encoding: utf-8

from sqlalchemy.orm import (contains_eager)
from sqlalchemy.orm import (joinedload, joinedload_all, subqueryload, subqueryload_all)
from sqlalchemy.orm.exc import NoResultFound
import pyramid.httpexceptions as exc

import pokedex.db.tables as t

from .. import db
from .. import helpers

def type_list(request):
    c = request.tmpl_context

    c.types = db.pokedex_session.query(t.Type) \
        .join(t.Type.names_local) \
        .filter(t.Type.damage_efficacies.any()) \
        .order_by(t.Type.names_table.name) \
        .options(contains_eager(t.Type.names_local)) \
        .options(joinedload('damage_efficacies')) \
        .all()

    if 'secondary' in request.params:
        try:
            c.secondary_type = db.get_by_name_query(
                    t.Type, request.params['secondary'].lower()) \
                .filter(t.Type.damage_efficacies.any()) \
                .options(joinedload('target_efficacies')) \
                .one()
        except NoResultFound:
            return exc.HTTPNotFound()

        c.secondary_efficacy = dict(
            (efficacy.damage_type, efficacy.damage_factor)
            for efficacy in c.secondary_type.target_efficacies
        )
    else:
        c.secondary_type = None
        c.secondary_efficacy = defaultdict(lambda: 100)

    # Count up a relative score for each type, both attacking and
    # defending.  Normal damage counts for 0; super effective counts for
    # +1; not very effective counts for -1.  Ineffective counts for -2.
    # With dual types, x4 is +2 and x1/4 is -2; ineffective is -4.
    # Everything is of course the other way around for defense.
    attacking_score_conversion = {
        400: +2,
        200: +1,
        100:  0,
            50: -1,
            25: -2,
            0: -2,
    }
    if c.secondary_type:
        attacking_score_conversion[0] = -4

    c.attacking_scores = defaultdict(int)
    c.defending_scores = defaultdict(int)
    for attacking_type in c.types:
        for efficacy in attacking_type.damage_efficacies:
            defending_type = efficacy.target_type
            factor = efficacy.damage_factor * \
                c.secondary_efficacy[attacking_type] // 100

            c.attacking_scores[attacking_type] += attacking_score_conversion[factor]
            c.defending_scores[defending_type] -= attacking_score_conversion[factor]

    return {}

def type_view(request):
    name = request.matchdict.get('name')
    c = request.tmpl_context

    try:
        c.type = db.get_by_name_query(t.Type, name).one()
    except NoResultFound:
        return exc.HTTPNotFound()

    ### Prev/next for header
    c.prev_type, c.next_type = helpers.prev_next(
        table=t.Type,
        current=c.type,
    )

    ### XXX cache after this

    # Eagerload a bit of type stuff
    db.pokedex_session.query(t.Type) \
        .filter_by(id=c.type.id) \
        .options(
            subqueryload('damage_efficacies'),
            joinedload('damage_efficacies.target_type'),
            subqueryload('target_efficacies'),
            joinedload('target_efficacies.damage_type'),

            # Move stuff
            subqueryload('moves'),
            joinedload('moves.damage_class'),
            joinedload('moves.generation'),
            joinedload('moves.move_effect'),
            joinedload('moves.type'),

            # Pokémon stuff
            subqueryload('pokemon'),
            joinedload('pokemon.abilities'),
            joinedload('pokemon.hidden_ability'),
            joinedload('pokemon.species'),
            subqueryload('pokemon.species.egg_groups'),
            joinedload('pokemon.types'),
            joinedload('pokemon.stats'),
        ) \
        .one()

    return {}
