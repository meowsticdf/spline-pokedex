# encoding: utf-8

import re

import pyramid.httpexceptions as exc
from pyramid.renderers import render_to_response

import pokedex.db.tables as t

#from spline.lib.helpers import flash
from .. import db, lib, helpers, splinehelpers

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

def _egg_unlock_cheat(request, cheat):
    """Easter egg that writes Pokédex data in the Pokémon font."""
    session = request.session
    c = request.tmpl_context
    cheat_key = "cheat_%s" % cheat
    session[cheat_key] = not session.get(cheat_key, False)
    session.save()
    c.this_cheat_key = cheat_key
    return render_to_response('/pokedex/cheat_unlocked.mako', {'session': session}, request=request)


def lookup(request):
    """Find a page in the Pokédex given a name.

    Also performs fuzzy search.
    """
    c = request.tmpl_context
    flash = lib.Flash(request.session) # XXX(pyramid)

    name = request.params.get('lookup', None)
    if not name:
        # Nothing entered.  What?  Where did you come from?
        # There's nothing sensible to do here.  Let's use an obscure status
        # code, like 204 No Content.
        return exc.HTTPNoContent()

    name = name.strip()
    lookup = name.lower()

    ### Special stuff that bypasses lookup
    if lookup == 'obdurate':
        # Pokémon flavor text in the D/P font
        return _egg_unlock_cheat(request, 'obdurate')


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
            flash(u"""Nothing in the Pokédex is exactly called "{0}".  """
                  u"""This is the only close match.""".format(name),
                  icon='spell-check-error')

        return redirect(helpers.resource_url(request, results[0].object, subpage=c.subpage))

    else:
        # Multiple matches.  Could be exact (e.g., Metronome) or a fuzzy
        # match.  Result page looks about the same either way
        c.input = name
        c.exact = results[0].exact
        c.results = results
        c.table_labels = table_labels
        return {}


def suggest(request):
    """Returns a JSON array of Pokédex lookup suggestions, compatible with
    the OpenSearch spec.
    """
    c = request.tmpl_context

    prefix = request.params.get('prefix', None)
    if not prefix:
        return '[]'

    valid_types = request.params.getall('type')

    suggestions = db.pokedex_lookup.prefix_lookup(
        prefix,
        valid_types=valid_types,
    )

    names = []     # actual terms that will appear in the list
    metadata = []  # parallel array of metadata my suggest widget uses
    for suggestion in suggestions:
        row = suggestion.object
        names.append(suggestion.name)
        meta = dict(
            type=row.__singlename__,
            indexed_name=suggestion.indexed_name,
        )

        # Get an accompanying image.  Moves get their type; abilities get
        # nothing; everything else gets the obvious corresponding icon
        # XXX uh, move this into a helper?
        image = None
        if isinstance(row, t.PokemonSpecies):
            image = u"pokemon/icons/{0}.png".format(row.id)
        elif isinstance(row, t.PokemonForm):
            if row.form_identifier:
                image = u"pokemon/icons/{0}-{1}.png".format(row.pokemon.species_id, row.form_identifier)
            else:
                image = u"pokemon/icons/{0}.png".format(row.pokemon.species_id)
        elif isinstance(row, t.Move):
            image = u"types/{1}/{0}.png".format(row.type.name.lower(),
                    c.game_language.identifier)
        elif isinstance(row, t.Type):
            image = u"types/{1}/{0}.png".format(row.name.lower(),
                    c.game_language.identifier)
        elif isinstance(row, t.Item):
            image = u"items/{0}.png".format(
                helpers.item_filename(row))

        if image:
            # n.b. route_url returns a fully qualified url
            meta['image'] = request.route_url('dex/media', subpath=image)

        # Give a country icon so JavaScript doesn't have to hardcore Spline
        # paths.  Don't *think* we need to give the long language name...
        meta['language'] = suggestion.iso3166
        # n.b. route_url returns a fully qualified url
        meta['language_icon'] = request.route_url(
            'static',
            subpath='spline/flags/{0}.png'.format(suggestion.iso3166),
        )

        metadata.append(meta)

    normalized_name = db.pokedex_lookup.normalize_name(prefix)
    if ':' in normalized_name:
        _, normalized_name = normalized_name.split(':', 1)

    data = [
        prefix,
        names,
        None,       # descriptions
        None,       # query URLs
        metadata,   # my metadata; outside the spec's range
        normalized_name,  # the key we actually looked for
    ]

    return data
