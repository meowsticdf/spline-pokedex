# encoding: utf-8

from __future__ import absolute_import, division

from collections import defaultdict, namedtuple
import colorsys
from itertools import groupby

from sqlalchemy.orm import (aliased, contains_eager, join)
from sqlalchemy.orm import (joinedload, joinedload_all, subqueryload, subqueryload_all)
from sqlalchemy.orm.exc import NoResultFound
from sqlalchemy.sql import and_, or_, not_
from sqlalchemy.sql import exists, func
import pyramid.httpexceptions as exc

import pokedex.db.tables as t

from .. import db
from .. import helpers as pokedex_helpers
from .locations import encounter_method_icons, encounter_condition_value_icons

def bar_color(hue, pastelness):
    """Returns a color in the form #rrggbb that has the provided hue and
    lightness/saturation equal to the given "pastelness".
    """
    r, g, b = colorsys.hls_to_rgb(hue, pastelness, pastelness)
    return "#%02x%02x%02x" % (r * 256, g * 256, b * 256)

def _pokemon_move_method_sort_key((method, _)):
    """Sorts methods by id, except that tutors and machines are bumped to the
    bottom, as they tend to be much longer than everything else.
    """
    # XXX see FakeMoveMethod for explanation of this abomination
    try:
        p = -method.pokemon.order
    except AttributeError:
        p = None
    if method.identifier in (u'tutor', u'machine'):
        return method.id + 1000, p
    else:
        return method.id, p

def _collapse_pokemon_move_columns(table, thing):
    """Combines adjacent identical columns in a pokemon_move structure.

    Arguments are the table structure (defined in comments below) and the
    Pokémon or move in question.

    Returns a list of column groups, each represented by a list of its columns,
    like `[ [ [gs, c] ], [ [rs, e], [fl] ], ... ]`
    """

    # What we really need to know is what versions are ultimately collapsed
    # into each column.  We also need to know how the columns are grouped into
    # generations.  So we need a list of lists of lists of version groups:
    move_columns = []

    # Only even consider versions in which this thing actually exists
    q = (db.pokedex_session.query(t.VersionGroup)
        .order_by(t.VersionGroup.order))

    if isinstance(thing, t.Pokemon):
        # If a Pokémon learns no moves in a particular version group, that
        # means it didn't exist in that group.  (n.b. Deoxys is particularly
        # weird in that some forms appear and then briefly disappear again, so
        # figuring out which group this form was introduced in isn't enough.)
        q = q.filter(t.VersionGroup.pokemon_moves.any(
            t.PokemonMove.pokemon_id == thing.id))
    else:
        # But a few moves exist but remain unused until midway through a gen,
        # so empty columns are useful; see e.g. Kinesis, Ice Burn
        q = q.filter(t.VersionGroup.generation_id >= thing.generation_id)

    gens = groupby(q, lambda vg: vg.generation_id)

    for gen, version_groups in gens:
        move_columns.append( [] ) # A new column group for this generation
        for i, version_group in enumerate(version_groups):
            if i == 0:
                # Can't collapse these versions anywhere!  Create a new column
                move_columns[-1].append( [version_group] )
                continue

            # Test to see if this version group column is identical to the one
            # immediately to its left; if so, we can combine them
            squashable = True
            for method, method_list in table:
                # Tutors are special; they will NEVER collapse, so ignore them
                # for now.  When we actually print the table, we'll concatenate
                # all the tutor cells instead of just using the first one like
                # with everything else
                if method.identifier == u'tutor':
                    continue

                # If a method doesn't appear in a version group at all,
                # it's always squashable.
                if method.id not in [m.id for m in version_group.pokemon_move_methods]:
                    # Squashable
                    continue

                # Now look at the preceding column, and compare with the first
                # applicable version group we find there
                for move, version_group_data in method_list:
                    data = version_group_data.get(version_group, None)
                    for vg in move_columns[-1][-1]:
                        if method.id not in [m.id for m in vg.pokemon_move_methods]:
                            continue
                        if data != version_group_data.get(vg, None):
                            # Not squashable
                            break
                    else:
                        # Looks squashable so far, try next move
                        continue

                    # We broke out – not squashable
                    break
                else:
                    # Looks squashable so far, try next method
                    continue

                break # We broke out and didn't get to continue—not squashable
            else:
                # Squashable; stick this version group in the previous column
                move_columns[-1][-1].append(version_group)
                continue

            # Not squashable; create a new column
            move_columns[-1].append( [version_group] )

    return move_columns

def _move_tutor_version_groups(table):
    """Tutored moves are never the same between version groups, so the column
    collapsing ignores tutors entirely.  This means that we might end up
    wanting to show several versions as having a tutor within a single column.
    So that "E, FRLG" lines up with "FRLG", there has to be a blank space for
    "E", which requires finding all the version groups that contain tutors.
    """

    move_tutor_version_groups = set()
    for method, method_list in table:
        if method.identifier != u'tutor':
            continue
        for move, version_group_data in method_list:
            move_tutor_version_groups.update(version_group_data.keys())

    return move_tutor_version_groups

def level_range(a, b):
    """If a and b are the same, returns 'L{a}'.  Otherwise, returns 'L{a}–{b}'.
    """

    if a == b:
        return u"L{0}".format(a)
    else:
        return u"L{0}–{1}".format(a, b)

class CombinedEncounter(object):
    """Represents several encounter rows, collapsed together.  Rarities and
    level ranges are combined correctly.

    Assumed to have the same method.  Also location and area and so forth, but
    those aren't actually needed.
    """
    def __init__(self, encounter=None):
        self.method = None
        self.rarity = 0
        self.min_level = 0
        self.max_level = 0

        if encounter:
            self.combine_with(encounter)

    def combine_with(self, encounter):
        if self.method and self.method != encounter.slot.method:
            raise ValueError(
                "Can't combine method {0} with {1}"
                .format(self.method.name, encounter.slot.method.name)
            )

        self.rarity += encounter.slot.rarity
        self.max_level = max(self.max_level, encounter.max_level)

        if not self.min_level:
            self.min_level = encounter.min_level
        else:
            self.min_level = min(self.min_level, encounter.min_level)

    @property
    def level(self):
        return level_range(self.min_level, self.max_level)

def _prev_next_species(species):
    """Returns a 2-tuple of the previous and next Pokémon species."""
    max_id = db.pokedex_session.query(t.PokemonSpecies).count()
    prev_species = db.pokedex_session.query(t.PokemonSpecies).get(
        (species.id - 1 - 1) % max_id + 1)
    next_species = db.pokedex_session.query(t.PokemonSpecies).get(
        (species.id - 1 + 1) % max_id + 1)
    return prev_species, next_species

def pokemon_view(request):
    name = request.matchdict.get('name')
    form = request.params.get('form', None)
    c = request.tmpl_context

    try:
        pokemon_q = db.pokemon_query(name, form)

        # Need to eagerload some, uh, little stuff
        pokemon_q = pokemon_q.options(
            joinedload(t.Pokemon.abilities, t.Ability.prose_local),
            joinedload(t.Pokemon.hidden_ability, t.Ability.prose_local),
            joinedload('species.evolution_chain.species'),
            joinedload('species.generation'),
            joinedload('items.item'),
            joinedload('items.version'),
            joinedload('species'),
            joinedload('species.color'),
            joinedload('species.habitat'),
            joinedload('species.shape'),
            joinedload('species.egg_groups'),
            subqueryload_all('stats.stat'),
            subqueryload_all('types.target_efficacies.damage_type'),
        )

        # Alright, execute
        c.pokemon = pokemon_q.one()
    except NoResultFound:
        raise exc.NotFound()

    ### Previous and next for the header
    c.prev_species, c.next_species = _prev_next_species(c.pokemon.species)

    # Some Javascript
    # XXX
    #c.javascripts.append(('pokedex', 'pokemon'))

    ### TODO: Let's cache this bitch
    #return self.cache_content(
    #    key=c.pokemon.identifier,
    #    template='/pokedex/pokemon.mako',
    #    do_work=self._do_pokemon,
    #)

    ### Type efficacy
    c.type_efficacies = defaultdict(lambda: 100)
    for target_type in c.pokemon.types:
        for type_efficacy in target_type.target_efficacies:
            c.type_efficacies[type_efficacy.damage_type] *= \
                type_efficacy.damage_factor

            # The defaultdict starts at 100, and every damage factor is
            # a percentage.  Dividing by 100 with every iteration turns the
            # damage factor into a decimal percentage taken of the starting
            # 100, without using floats and regardless of number of types
            c.type_efficacies[type_efficacy.damage_type] //= 100

    ### Breeding compatibility
    # To simplify this list considerably, we want to find the BASE FORM of
    # every Pokémon compatible with this one.  The base form is either:
    # - a Pokémon that has breeding groups and no evolution parent, or
    # - a Pokémon whose parent has no breeding groups (i.e. 15 only)
    #   and no evolution parent.
    # The below query self-joins `pokemon` to itself and tests the above
    # conditions.
    # ASSUMPTION: Every base-form Pokémon in a breedable family can breed.
    # ASSUMPTION: Every family has the same breeding groups throughout.
    if c.pokemon.species.gender_rate == -1:
        # Genderless; Ditto only
        ditto = db.pokedex_session.query(t.PokemonSpecies) \
            .filter_by(identifier=u'ditto').one()
        c.compatible_families = [ditto]
    elif c.pokemon.species.egg_groups[0].id == 15:
        # No Eggs group
        c.compatible_families = []
    else:
        parent_a = aliased(t.PokemonSpecies)
        grandparent_a = aliased(t.PokemonSpecies)
        egg_group_ids = [group.id for group in c.pokemon.species.egg_groups]
        q = db.pokedex_session.query(t.PokemonSpecies)
        q = q.join(t.PokemonEggGroup) \
                .outerjoin((parent_a, t.PokemonSpecies.parent_species)) \
                .outerjoin((grandparent_a, parent_a.parent_species))
        # This is a "base form" iff either:
        where = or_(
            # This is the root form (no parent)
            # (It has to be breedable too, but we're filtering by
            # an egg group so that's granted)
            parent_a.id == None,
            # Or this can breed and evolves from something that
            # can't
            and_(parent_a.egg_groups.any(id=15),
                    grandparent_a.id == None),
        )
        # Can only breed with pokémon we share an egg group with
        where &= t.PokemonEggGroup.egg_group_id.in_(egg_group_ids)
        # Can't breed with genderless pokémon
        where &= t.PokemonSpecies.gender_rate != -1
        # Male-only pokémon can't breed with other male-only pokémon
        # Female-only pokémon can't breed with other female-only pokémon
        if c.pokemon.species.gender_rate in (0, 8):
            where &= t.PokemonSpecies.gender_rate != c.pokemon.species.gender_rate
        # Ditto can breed with anything
        where |= t.PokemonEggGroup.egg_group_id == 13
        q = q.filter(where)
        q = q.options(joinedload('default_form')) \
                .order_by(t.PokemonSpecies.id)
        c.compatible_families = q.all()

    ### Wild held items
    # Stored separately per version due to *rizer shenanigans (grumble).
    # Items also sometimes change over version groups within a generation.
    # So in some 99.9% of cases we want to merge them to some extent,
    # usually collapsing an entire version group or an entire generation.
    # Thus we store these as:
    #   generation => { (version, ...) => [ (item, rarity), ... ] }
    # In the case of all versions within a generation being merged, the
    # key is None instead of a tuple of version objects.
    c.held_items = {}

    # First group by the things we care about
    # n.b.: the keys are tuples of versions, not individual versions!
    version_held_items = {}
    # Preload with a list of versions so we know which ones are empty
    generations = db.pokedex_session.query(t.Generation) \
        .options( joinedload('versions') ) \
        .filter(t.Generation.id >= max(3, c.pokemon.species.generation_id))
    for generation in generations:
        version_held_items[generation] = {}
        for version in generation.versions:
            version_held_items[generation][version,] = []

    for pokemon_item in c.pokemon.items:
        generation = pokemon_item.version.generation

        version_held_items[generation][pokemon_item.version,] \
            .append((pokemon_item.item, pokemon_item.rarity))

    # Then group these into the form above
    for generation, gen_held_items in version_held_items.items():
        # gen_held_items: { (versions...): [(item, rarity)...] }
        # Group by item, rarity, sorted by version...
        inverted_held_items = defaultdict(tuple)
        for version_tuple, item_rarity_list in \
            sorted(gen_held_items.items(), key=lambda (k, v): k[0].id):

            inverted_held_items[tuple(item_rarity_list)] += version_tuple

        # Then flip back to versions as keys
        c.held_items[generation] = {}
        for item_rarity_tuple, version_tuple in inverted_held_items.items():
            c.held_items[generation][version_tuple] = item_rarity_tuple

    ### Evolution
    # Format is a matrix as follows:
    # [
    #   [ None, Eevee, Vaporeon, None ]
    #   [ None, None, Jolteon, None ]
    #   [ None, None, Flareon, None ]
    #   ... etc ...
    # ]
    # That is, each row is a physical row in the resulting table, and each
    # contains four elements, one per row: Baby, Base, Stage 1, Stage 2.
    # The Pokémon are actually dictionaries with 'pokemon' and 'span' keys,
    # where the span is used as the HTML cell's rowspan -- e.g., Eevee has a
    # total of seven descendents, so it would need to span 7 rows.
    c.evolution_table = []
    # Prefetch the evolution details
    family = db.pokedex_session.query(t.PokemonSpecies) \
        .filter(t.PokemonSpecies.evolution_chain_id ==
                c.pokemon.species.evolution_chain_id) \
        .options(
            subqueryload('evolutions'),
            joinedload('evolutions.trigger'),
            joinedload('evolutions.trigger_item'),
            joinedload('evolutions.held_item'),
            joinedload('evolutions.location'),
            joinedload('evolutions.known_move'),
            joinedload('evolutions.party_species'),
            joinedload('evolutions.gender'),
            joinedload('parent_species'),
            joinedload('default_form'),
        ) \
        .all()
    # Strategy: build this table going backwards.
    # Find a leaf, build the path going back up to its root.  Remember all
    # of the nodes seen along the way.  Find another leaf not seen so far.
    # Build its path backwards, sticking it to a seen node if one exists.
    # Repeat until there are no unseen nodes.
    seen_nodes = {}
    while True:
        # First, find some unseen nodes
        unseen_leaves = []
        for species in family:
            if species in seen_nodes:
                continue

            children = []
            # A Pokémon is a leaf if it has no evolutionary children, so...
            for possible_child in family:
                if possible_child in seen_nodes:
                    continue
                if possible_child.parent_species == species:
                    children.append(possible_child)
            if len(children) == 0:
                unseen_leaves.append(species)

        # If there are none, we're done!  Bail.
        # Note that it is impossible to have any unseen non-leaves if there
        # are no unseen leaves; every leaf's ancestors become seen when we
        # build a path to it.
        if len(unseen_leaves) == 0:
            break

        unseen_leaves.sort(key=lambda x: x.id)
        leaf = unseen_leaves[0]

        # root, parent_n, ... parent2, parent1, leaf
        current_path = []

        # Finally, go back up the tree to the root
        current_species = leaf
        while current_species:
            # The loop bails just after current_species is no longer the
            # root, so this will give us the root after the loop ends;
            # we need to know if it's a baby to see whether to indent the
            # entire table below
            root_pokemon = current_species

            if current_species in seen_nodes:
                current_node = seen_nodes[current_species]
                # Don't need to repeat this node; the first instance will
                # have a rowspan
                current_path.insert(0, None)
            else:
                current_node = {
                    'species': current_species,
                    'span':    0,
                }
                current_path.insert(0, current_node)
                seen_nodes[current_species] = current_node

            # This node has one more row to span: our current leaf
            current_node['span'] += 1

            current_species = current_species.parent_species

        # We want every path to have four nodes: baby, basic, stage 1 and 2.
        # Every root node is basic, unless it's defined as being a baby.
        # So first, add an empty baby node at the beginning if this is not
        # a baby.
        # We use an empty string to indicate an empty cell, as opposed to a
        # complete lack of cell due to a tall cell from an earlier row.
        if not root_pokemon.is_baby:
            current_path.insert(0, '')
        # Now pad to four if necessary.
        while len(current_path) < 4:
            current_path.append('')

        c.evolution_table.append(current_path)

    ### Stats
    # This takes a lot of queries  :(
    c.stats = {}  # stat_name => { border, background, percentile }
                    #              (also 'value' for total)
    stat_total = 0
    total_stat_rows = db.pokedex_session.query(t.PokemonStat) \
                                        .filter_by(stat=c.pokemon.stats[0].stat) \
                                        .count()
    physical_attack = None
    special_attack = None
    for pokemon_stat in c.pokemon.stats:
        stat_info = c.stats[pokemon_stat.stat.name] = {}
        stat_total += pokemon_stat.base_stat
        q = db.pokedex_session.query(t.PokemonStat) \
                            .filter_by(stat=pokemon_stat.stat)
        less = q.filter(t.PokemonStat.base_stat < pokemon_stat.base_stat) \
                .count()
        equal = q.filter(t.PokemonStat.base_stat == pokemon_stat.base_stat) \
                    .count()
        percentile = (less + equal * 0.5) / total_stat_rows
        stat_info['percentile'] = percentile

        # Colors for the stat bars, based on percentile
        stat_info['background'] = bar_color(percentile, 0.9)
        stat_info['border'] = bar_color(percentile, 0.8)

    c.better_damage_class = c.pokemon.better_damage_class

    # Percentile for the total
    # Need to make a derived table that fakes pokemon_id, total_stats
    stat_sum_tbl = db.pokedex_session.query(
            func.sum(t.PokemonStat.base_stat).label('stat_total')
        ) \
        .group_by(t.PokemonStat.pokemon_id) \
        .subquery()

    q = db.pokedex_session.query(stat_sum_tbl)
    less = q.filter(stat_sum_tbl.c.stat_total < stat_total).count()
    equal = q.filter(stat_sum_tbl.c.stat_total == stat_total).count()
    percentile = (less + equal * 0.5) / total_stat_rows
    c.stats['total'] = {
        'percentile': percentile,
        'value': stat_total,
        'background': bar_color(percentile, 0.9),
        'border': bar_color(percentile, 0.8),
    }

    ### Pokéathlon stats
    # Unown collapses to letters and punctuation.  Shellos and Gastrodon
    # can collapse entirely.  Nothing else collapses at all.  (Arceus
    # /could/ have two pairs of types collapse, but who cares.)

    # Show all forms' stats for the base form, or else just this form's
    forms = [form for form in c.pokemon.forms or [c.pokemon.unique_form]
                if form.pokeathlon_stats]

    if not forms:
        # No stats
        c.pokeathlon_stats = None
    elif len(forms) == 1 or c.pokemon.id in (422, 423):
        # Only one set of stats, or Shellos/Gastrodon
        c.pokeathlon_stats = [(None, forms[0].pokeathlon_stats)]
    elif c.pokemon.id == 201:
        # Use Unown A's stats for all the letters and !'s stats for ! and ?
        c.pokeathlon_stats = [('A-Z', forms[0].pokeathlon_stats),
                                ('! and ?', forms[26].pokeathlon_stats)]
    else:
        # Different stats for every form
        c.pokeathlon_stats = [(form.form_name or 'Normal Form',
                                form.pokeathlon_stats) for form in forms]

    ### Sizing
    c.trainer_height = pokedex_helpers.trainer_height
    c.trainer_weight = pokedex_helpers.trainer_weight
    heights = dict(pokemon=c.pokemon.height, trainer=c.trainer_height)
    c.heights = pokedex_helpers.scale_sizes(heights)
    # Strictly speaking, weight takes three dimensions.  But the real
    # measurement here is just "space taken up", and these are sprites, so
    # the space they actually take up is two-dimensional.
    weights = dict(pokemon=c.pokemon.weight, trainer=c.trainer_weight)
    c.weights = pokedex_helpers.scale_sizes(weights, dimensions=2)

    ### Encounters -- briefly
    # One row per version, then a list of places the Pokémon appears.
    # version => method => location_area => conditions => CombinedEncounters
    c.locations = defaultdict(
        lambda: defaultdict(
            lambda: defaultdict(
                lambda: defaultdict(
                    CombinedEncounter
                )
            )
        )
    )

    q = db.pokedex_session.query(t.Encounter) \
        .filter_by(pokemon=c.pokemon) \
        .options(
            joinedload_all('condition_values'),
            joinedload_all('version'),
            joinedload_all('slot.method'),
            joinedload_all('location_area.location'),
        )
    for encounter in q:
        condition_values = [cv for cv in encounter.condition_values
                                if not cv.is_default]
        c.locations[encounter.version] \
                    [encounter.slot.method] \
                    [encounter.location_area] \
                    [tuple(condition_values)].combine_with(encounter)

    # Strip each version+location down to just the condition values that
    # are the most common per method
    # Results in:
    # version => location_area => method => (conditions, combined_encounter)
    for version, method_etc in c.locations.items():
        for method, area_condition_encounters \
            in method_etc.items():
            for location_area, condition_encounters \
                in area_condition_encounters.items():

                # Sort these by rarity
                condition_encounter_items = condition_encounters.items()
                condition_encounter_items.sort(
                    key=lambda (conditions, combined_encounter):
                        combined_encounter.rarity
                )

                # Use the last one, which is most common
                area_condition_encounters[location_area] \
                    = condition_encounter_items[-1]

    # Used for prettiness
    c.encounter_method_icons = encounter_method_icons

    ### Moves
    # Oh no.
    # Moves are grouped by method.
    # Within a method is a list of move rows.
    # A move row contains a level or other status per version group, plus
    # a move id.
    # Thus: ( method, [ (move, { version_group => data, ... }), ... ] )
    # First, though, we make a dictionary for quick access to each method's
    # list.
    # "data" is a dictionary of whatever per-version information is
    # appropriate for this move method, such as a TM number or level.
    move_methods = defaultdict(list)
    q = db.pokedex_session.query(t.PokemonMove) \
        .outerjoin((t.Machine, t.PokemonMove.machine)) \
        .outerjoin((t.PokemonMoveMethod, t.PokemonMove.method))
    # Evolved Pokémon ought to show their predecessors' egg moves.
    # So far, no species evolves from a parent with multiple functional
    # forms, but don't rely on that
    possible_ancestors = set([c.pokemon])
    ancestors = []
    while possible_ancestors:
        ancestor = possible_ancestors.pop()
        ancestors.append(ancestor)
        parent_species = ancestor.species.parent_species
        if parent_species:
            possible_ancestors.update(parent_species.pokemon)
    if ancestors:
        # Include any moves learnable by an ancestor...
        ancestor_ids = [p.id for p in ancestors]
        ancestor_ids.append(c.pokemon.id)
        q = q.filter(t.PokemonMove.pokemon_id.in_(ancestor_ids))

        # ... in a generation where this Pokémon actually exists...
        q = q.join(t.VersionGroup, t.PokemonMove.version_group)
        q = q.filter(t.VersionGroup.generation_id >=
                        c.pokemon.default_form.version_group.generation_id)

        # That AREN'T learnable by this Pokémon.  This NOT EXISTS strips
        # out moves that are also learned by a "higher-ordered" Pokémon.
        pm_outer = t.PokemonMove
        p_outer = t.Pokemon
        pm_inner = aliased(t.PokemonMove)
        p_inner = aliased(t.Pokemon)

        from_inner = join(pm_inner, p_inner, onclause=pm_inner.pokemon)
        clause = exists(from_inner.select()).where(and_(
            pm_outer.version_group_id == pm_inner.version_group_id,
            pm_outer.move_id == pm_inner.move_id,
            pm_outer.pokemon_move_method_id == pm_inner.pokemon_move_method_id,
            pm_inner.pokemon_id.in_(ancestor_ids),
            p_outer.order < p_inner.order,
        ))

        q = q.outerjoin(t.PokemonMove.pokemon).filter(~ clause)
    else:
        q = q.filter(t.PokemonMove.pokemon_id == c.pokemon.id)
    # Grab the rows with a manual query so we can sort them in about the
    # order they go in the table.  This should keep it as compact as
    # possible.  Levels go in level order, and machines go in TM number
    # order
    q = q.options(
                contains_eager(t.PokemonMove.machine),
                contains_eager(t.PokemonMove.method),
                # n.b: contains_eager interacts badly with joinedload with
                # innerjoin=True.  Disable the inner joining explicitly.
                # See: http://www.sqlalchemy.org/trac/ticket/2120
                joinedload(
                    t.PokemonMove.machine, t.Machine.version_group,
                    innerjoin=False),
                joinedload_all('move.damage_class'),
                joinedload_all(t.PokemonMove.move,
                    t.Move.move_effect,
                    t.MoveEffect.prose_local),
                joinedload_all('move.type'),
                joinedload_all('version_group'),
            ) \
        .order_by(t.PokemonMove.level.asc(),
                    t.Machine.machine_number.asc(),
                    t.PokemonMove.order.asc(),
                    t.PokemonMove.version_group_id.asc()) \
        .all()
    # TODO this nonsense is to allow methods that don't actually exist,
    # such as for parent's egg moves.  should go away once move tables get
    # their own rendery class
    FakeMoveMethod = namedtuple('FakeMoveMethod',
        ['id', 'name', 'identifier', 'description', 'pokemon', 'version_groups'])
    methods_cache = {}
    def find_method(pm):
        key = pm.method, pm.pokemon
        if key not in methods_cache:
            methods_cache[key] = FakeMoveMethod(
                id=pm.method.id, name=pm.method.name,
                identifier=pm.method.identifier,
                description=pm.method.description,
                pokemon=pm.pokemon,
                version_groups=tuple(pm.method.version_groups))
        return methods_cache[key]

    for pokemon_move in q:
        method = find_method(pokemon_move)
        method_list = move_methods[method]
        this_vg = pokemon_move.version_group

        # Create a container for data for this method and version(s)
        vg_data = dict()

        # TMs need to know their own TM number
        if method.identifier == u'machine':
            vg_data['machine'] = pokemon_move.machine.machine_number

        # Find the best place to insert a row.
        # In general, we just want the move names in order, so we can just
        # tack rows on and sort them at the end.  However!  Level-up moves
        # must stay in the same order within a version group, and TMs are
        # similarly ordered by number.  So we have to do some special
        # ordering here.
        # These two vars are the boundaries of where we can find or insert
        # a new row.  Only level-up moves have these restrictions
        lower_bound = None
        upper_bound = None
        if method.identifier in (u'level-up', u'machine'):
            vg_data['sort'] = (pokemon_move.level,
                                vg_data.get('machine', None),
                                pokemon_move.order)
            vg_data['level'] = pokemon_move.level

            # Find the next-lowest and next-highest rows.  Our row must fit
            # between those
            for i, (move, version_group_data) in enumerate(method_list):
                if this_vg not in version_group_data:
                    # Can't be a bound; not related to this version!
                    continue

                if version_group_data[this_vg]['sort'] > vg_data['sort']:
                    if not upper_bound or i < upper_bound:
                        upper_bound = i
                if version_group_data[this_vg]['sort'] < vg_data['sort']:
                    if not lower_bound or i > lower_bound:
                        lower_bound = i

        # We're using Python's slice syntax, which includes the lower bound
        # and excludes the upper.  But we want to exclude both, so bump the
        # lower bound
        if lower_bound != None:
            lower_bound += 1

        # Check for a free existing row for this move; if one exists, we
        # can just add our data to that same row.
        # It's also possible that an existing row for this move can be
        # shifted forwards into our valid range, if there are no
        # intervening rows with levels in the same version groups that that
        # row has.  This is unusual, but happens when a lot of moves have
        # been shuffled around multiple times, like with Pikachu
        valid_row = None
        for i, table_row in enumerate(method_list[0:upper_bound]):
            move, version_group_data = table_row

            # If we've already found a row for version X outside our valid
            # range but run across another row with a level for X, that row
            # cannot be moved up, so it's not usable
            if valid_row and set(valid_row[1].keys()).intersection(
                                    set(version_group_data.keys())):
                valid_row = None

            if move == pokemon_move.move \
                and this_vg not in version_group_data:

                valid_row = table_row
                # If we're inside the valid range, just take the first row
                # we find.  If we're outside it, we want the last possible
                # row to avoid shuffling the table too much.  So only break
                # if this row is inside lb/ub
                if i >= lower_bound:
                    break

        if valid_row:
            if method_list.index(valid_row) < lower_bound:
                # Move the row up if necessary
                method_list.remove(valid_row)
                method_list.insert(lower_bound, valid_row)
            valid_row[1][this_vg] = vg_data
            continue

        # Otherwise, just make a new row and stuff it in.
        # Rows are sorted by level before version group.  If we see move X
        # for a level, then move Y for another game, then move X for that
        # other game, the two X's should be able to collapse.  Thus we put
        # the Y before the first X to leave space for the second X -- that
        # is, add new rows as early in the list as possible
        new_row = pokemon_move.move, { this_vg: vg_data }
        method_list.insert(lower_bound or 0, new_row)

    # Convert dictionary to our desired list of tuples
    c.moves = move_methods.items()
    c.moves.sort(key=_pokemon_move_method_sort_key)

    # Sort non-level moves by name
    for method, method_list in c.moves:
        if method.identifier in (u'level-up', u'machine'):
            continue
        method_list.sort(key=lambda (move, version_group_data): move.name)

    # Finally, collapse identical columns within the same generation
    c.move_columns \
        = _collapse_pokemon_move_columns(table=c.moves, thing=c.pokemon)

    # Grab list of all the version groups with tutor moves
    c.move_tutor_version_groups = _move_tutor_version_groups(c.moves)

    return {}


def pokemon_flavor_view(request):
    name = request.matchdict.get('name')
    form = request.params.get('form', None)
    c = request.tmpl_context

    try:
        c.form = db.pokemon_form_query(name, form=form).one()
    except NoResultFound:
        raise exc.NotFound()

    c.pokemon = c.form.pokemon

    ### Previous and next for the header
    c.prev_species, c.next_species = _prev_next_species(c.pokemon.species)

    # Some Javascript
    # XXX(pyramid)
    #c.javascripts.append(('pokedex', 'pokemon'))

    # XXX(pyramid) cache me
    #return self.cache_content(
    #    key=c.form.identifier,
    #    template='/pokedex/pokemon_flavor.mako',
    #    do_work=self._do_pokemon_flavor,
    #)

    c.sprites = {}

    config = request.registry.settings
    def sprite_exists(directory):
        """Return whether or not a sprite exists for this Pokémon in the
        specified directory, checking if need be.

        Avoids calling resource_exists() multiple times per sprite.
        """

        if 'animated' in directory:
            extension = 'gif'
        elif 'dream-world' in directory:
            extension = 'svg'
        else:
            extension = 'png'

        # n.b. calling dict.setdefault always evaluates the default
        if directory not in c.sprites:
            c.sprites[directory] = pokedex_helpers.pokemon_has_media(
                c.form, directory, extension, config)
        return c.sprites[directory]
    c.sprite_exists = sprite_exists

    ### Sizing
    c.trainer_height = pokedex_helpers.trainer_height
    c.trainer_weight = pokedex_helpers.trainer_weight

    heights = {'pokemon': c.pokemon.height, 'trainer': c.trainer_height}
    c.heights = pokedex_helpers.scale_sizes(heights)

    # Strictly speaking, weight takes three dimensions.  But the real
    # measurement here is just "space taken up", and these are sprites, so
    # the space they actually take up is two-dimensional.
    weights = {'pokemon': c.pokemon.weight, 'trainer': c.trainer_weight}
    c.weights = pokedex_helpers.scale_sizes(weights, dimensions=2)

    return {}


def pokemon_locations_view(request):
    """Spits out a page listing detailed location information for this
    Pokémon.
    """
    name = request.matchdict.get('name')
    c = request.tmpl_context

    try:
        c.pokemon = db.pokemon_query(name).one()
    except NoResultFound:
        raise exc.NotFound()

    ### Previous and next for the header
    c.prev_species, c.next_species = _prev_next_species(c.pokemon.species)

    # Cache it yo
    # XXX(pyramid)
    #return self.cache_content(
    #    key=c.pokemon.identifier,
    #    template='/pokedex/pokemon_locations.mako',
    #    do_work=self._do_pokemon_locations,
    #)

    # For the most part, our data represents exactly what we're going to
    # show.  For a given area in a given game, this Pokémon is guaranteed
    # to appear some x% of the time no matter what the state of the world
    # is, and various things like swarms or the radar may add on to this
    # percentage.

    # Encounters are grouped by region -- <h1>s.
    # Then by method -- table sections.
    # Then by area -- table rows.
    # Then by version -- table columns.
    # Finally, condition values associated with levels/rarity.
    q = db.pokedex_session.query(t.Encounter) \
        .options(
            joinedload_all('condition_values'),
            joinedload_all('version'),
            joinedload_all('slot.method'),
            joinedload_all('location_area.location'),
        )\
        .filter(t.Encounter.pokemon == c.pokemon)

    # region => method => area => version => condition =>
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

    # Locations cluster by region, primarily to avoid having a lot of rows
    # where one version group or the other is blank; that doesn't make for
    # fun reading.  To put the correct version headers in each region
    # table, we need to know what versions correspond to which regions.
    # Normally, this can be done by examining region.version_groups.
    # However, some regions (Kanto) appear in a ridiculous number of games.
    # To avoid an ultra-wide table when not necessary, only *generations*
    # that actually contain this Pokémon should appear.
    # So if the Pokémon appears in Kanto in Crystal, show all of G/S/C.  If
    # it doesn't appear in any of the three, show none of them.
    # Last but not least, show generations in reverse order, so the more
    # important (i.e., recent) versions are on the left.
    # Got all that?
    region_generations = defaultdict(set)

    for encounter in q.all():
        # Fetches the list of encounters that match this region, version,
        # method, etc.
        region = encounter.location_area.location.region

        # n.b.: conditions and values must be tuples because lists aren't
        # hashable.
        encounter_bits = grouped_encounters \
            [region] \
            [encounter.slot.method] \
            [encounter.location_area] \
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

        # Remember that this generation appears in this region
        region_generations[region].add(encounter.version.version_group.generation)

    c.grouped_encounters = grouped_encounters

    # Pass some data/functions
    c.encounter_method_icons = encounter_method_icons
    c.encounter_condition_value_icons = encounter_condition_value_icons
    c.level_range = level_range

    # See above.  Versions for each region are those in that region that
    # are part of a generation where this Pokémon appears -- in reverse
    # generation order.
    c.region_versions = defaultdict(list)
    for region, generations in region_generations.items():
        for version_group in region.version_groups:
            if version_group.generation not in generations:
                continue
            c.region_versions[region][0:0] = version_group.versions

    return {}


def pokemon_list(request):
    return {}
