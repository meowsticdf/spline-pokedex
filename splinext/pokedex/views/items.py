# encoding: utf-8

from collections import defaultdict

from sqlalchemy.orm import (joinedload, joinedload_all, subqueryload, subqueryload_all)
from sqlalchemy.orm.exc import NoResultFound
import pyramid.httpexceptions as exc

import pokedex.db.tables as t

from .. import db
from .. import helpers
from . import errors

redirect = exc.HTTPFound

def item_list(request):
    c = request.tmpl_context
    c.item_pockets = db.pokedex_session.query(t.ItemPocket) \
        .order_by(t.ItemPocket.id.asc())
    return {}


def pocket_view(request):
    pocket = request.matchdict.get('pocket')
    c = request.tmpl_context

    try:
        c.item_pocket = db.pokedex_session.query(t.ItemPocket) \
            .filter(t.ItemPocket.identifier == pocket) \
            .options(
                joinedload_all('categories.items.berry'),
                joinedload_all('categories.items.prose_local'),
            ) \
            .one()
    except NoResultFound:
        # It's possible this is an old item URL; redirect if so
        try:
            item = db.get_by_name_query(t.Item, pocket).one()
            return redirect(helpers.resource_url(request, item))
        except NoResultFound:
            raise exc.HTTPNotFound()

    # OK, got a valid pocket

    # Eagerload TM info if it's actually needed
    if c.item_pocket.identifier == u'machines':
        db.pokedex_session.query(t.ItemPocket) \
            .options(joinedload_all('categories.items.machines.move.type')) \
            .get(c.item_pocket.id)

    c.item_pockets = db.pokedex_session.query(t.ItemPocket) \
        .order_by(t.ItemPocket.id.asc())

    return {}


def item_view(request):
    pocket = request.matchdict.get('pocket')
    name = request.matchdict.get('name')
    c = request.tmpl_context

    try:
        c.item = db.get_by_name_query(t.Item, name).one()
    except NoResultFound:
        return errors.notfound(request, t.Item, name)
    except MultipleResultsFound:
        # Bad hack to fix having duplicate items with the same name (e.g.
        # bicycles, z-crystals)
        c.item = db.get_by_name_query(t.Item, name).first()

    # These are used for their item linkage
    c.growth_mulch = db.pokedex_session.query(t.Item) \
        .filter_by(identifier=u'growth-mulch').one()
    c.damp_mulch = db.pokedex_session.query(t.Item) \
        .filter_by(identifier=u'damp-mulch').one()

    # Pokémon that can hold this item are per version; break this up into a
    # two-dimensional structure of pokemon => version => rarity
    c.holding_pokemon = defaultdict(lambda: defaultdict(int))
    held_generations = set()
    for pokemon_item in c.item.pokemon:
        c.holding_pokemon[pokemon_item.pokemon][pokemon_item.version] = pokemon_item.rarity
        held_generations.add(pokemon_item.version.generation)

    # Craft a list of versions, collapsed into columns, grouped by gen
    held_generations = sorted(held_generations, key=lambda gen: gen.id)
    c.held_version_columns = []
    for generation in held_generations:
        # Oh boy!  More version collapsing logic!
        # Try to make this as simple as possible: have a running list of
        # versions in some column, then switch to a new column when any
        # rarity changes
        c.held_version_columns.append( [[]] )  # New colgroup, empty column
        last_version = None
        for version in generation.versions:
            # If the any of the rarities changed, this version needs to
            # begin a new column
            if last_version and any(
                rarities[last_version] != rarities[version]
                for rarities in c.holding_pokemon.values()
            ):
                c.held_version_columns[-1].append([])

            c.held_version_columns[-1][-1].append(version)
            last_version = version

    return {}
