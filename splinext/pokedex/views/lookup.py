# encoding: utf-8

import re

import pyramid.httpexceptions as exc

import pokedex.db.tables as t

from spline.lib.helpers import flash
from .. import db, helpers

# Used by lookup disambig pages
table_labels = {
    t.Ability: 'ability',
    t.Item: 'item',
    t.Location: 'location',
    t.Move: 'move',
    t.Nature: 'nature',
    t.PokemonSpecies: u'Pokémon',
    t.PokemonForm: u'Pokémon form',
    t.Type: 'type',

    t.ConquestKingdom: u'Conquest kingdom',
    t.ConquestWarrior: u'Conquest warrior',
    t.ConquestWarriorSkill: u'Conquest warrior skill',
}

redirect = exc.HTTPFound

def lookup(request):
    """Find a page in the Pokédex given a name.

    Also performs fuzzy search.
    """
    c = request.tmpl_context

    name = request.params.get('lookup', None)
    if not name:
        # Nothing entered.  What?  Where did you come from?
        # There's nothing sensible to do here.  Let's use an obscure status
        # code, like 204 No Content.
        abort(204)

    name = name.strip()
    lookup = name.lower()

    ### Special stuff that bypasses lookup
    if lookup == 'obdurate':
        # Pokémon flavor text in the D/P font
        return self._egg_unlock_cheat('obdurate')


    ### Regular lookup
    valid_types = []
    c.subpage = None
    # Subpage suffixes: 'flavor' and 'locations' for Pokémon bits
    if lookup.endswith((u' flavor', u' flavour')):
        c.subpage = 'flavor'
        valid_types = [u'pokemon_species', u'pokemon_forms']
        name = re.sub('(?i) flavou?r$', '', name)
    elif lookup.endswith(u' locations'):
        c.subpage = 'locations'
        valid_types = [u'pokemon_species', u'pokemon_forms']
        name = re.sub('(?i) locations$', '', name)
    elif lookup.endswith(u' conquest'):
        c.subpage = 'conquest'
        valid_types = [u'pokemon_species', u'moves', u'abilities']
        name = re.sub('(?i) conquest$', '', name)

    results = db.pokedex_lookup.lookup(name, valid_types=valid_types)

    if len(results) == 0:
        # Nothing found
        # XXX real error page
        raise exc.HTTPNotFound()

    elif len(results) == 1:
        # Only one possibility!  Hooray!

        if not results[0].exact:
            # Wasn't an exact match, but we can only figure out one thing
            # the user might have meant, so redirect to it anyway
            #h.flash(u"""Nothing in the Pokédex is exactly called "{0}".  """
            #        u"""This is the only close match.""".format(name),
            #        icon='spell-check-error')
            pass # XXX

        return redirect(helpers.resource_url(request, results[0].object, subpage=c.subpage))

    else:
        # Multiple matches.  Could be exact (e.g., Metronome) or a fuzzy
        # match.  Result page looks about the same either way
        c.input = name
        c.exact = results[0].exact
        c.results = results
        c.table_labels = table_labels
        return {}
