<%! from itertools import groupby, chain, repeat %>
<%! import os, warnings %>

<%def name="pokedex_img(src, **attr)"><%
    # TODO: routing
    return h.HTML.img(src=request.route_path('dex/media', subpath=src), **attr)
%></%def>

<%def name="chrome_img(src, **attr)"><%
    return h.HTML.img(src=h.static_uri('pokedex', 'images/' + src), **attr)
%></%def>

## XXX Should these be able to promote to db objects, rather than demoting to
## strings and integers?  If so, how to do that without requiring db access
## from here?
<%def name="generation_icon(generation)"><%
    """Returns a generation icon, given a generation number."""
    # Convert generation to int if necessary
    if not isinstance(generation, int):
        generation = generation.id


    return chrome_img('versions/generation-%s.png' % generation,
            alt=_(u"Generation %d") % generation,
            title=_(u"Generation %d") % generation)
%></%def>

<%def name="version_icons(*versions, **kwargs)"><%
    """Returns some version icons, given a list of version names.

    """
    # python's argument_list syntax is kind of limited here
    version_icons = u''
    comma = chain([u''], repeat(u', '))
    for version in versions:
        # Convert version to string if necessary
        if isinstance(version, basestring):
            identifier = h.pokedex.filename_from_name(version)
            name = version
        else:
            identifier = version.identifier
            name = version.name

        version_icons += h.HTML.img(
                src=h.static_uri('pokedex', 'images/versions/%s.png' % identifier),
                alt=comma.next() + name,
                title=name)

    return version_icons
%></%def>

<%def name="version_group_icon(version_group)"><%
    return version_icons(*version_group.versions)
    # XXX this is for the combined pixely version group icons i made
    names = ', '.join(version.name for version in version_group.versions)
    return h.HTML.img(
        src=h.static_uri('pokedex', 'images/versions/%s.png' % (
            '-'.join(version.identifier for version in version_group.versions))),
        alt=names,
        title=names)
%></%def>


<%def name="pokemon_has_media(pokemon_form, prefix, ext, use_form=True)"><%
    """Determine whether a file exists in the specified directory for the
    specified Pokémon form.
    """
    # TODO share this somewhere
    media_dir = config.get('spline-pokedex.media_directory', None)
    if not media_dir:
        warnings.warn(
            "No media_directory found; "
            "you may want to clone pokedex-media.git")
        return False

    if use_form:
        kwargs = dict(form=pokemon_form)
    else:
        kwargs = dict()

    return os.path.exists(os.path.join(media_dir,
        pokemon_media_path(pokemon_form.species, prefix, ext, **kwargs)))
%></%def>

<%def name="pokemon_media_path(pokemon_species, prefix, ext, form=None)"><%
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
%></%def>

<%def name="species_image(pokemon_species, prefix='main-sprites/black-white', **attr)"><%
    u"""Returns an <img> tag for a Pokémon species image."""

    default_text = pokemon_species.name

    if 'animated' in prefix:
        ext = 'gif'
    else:
        ext = 'png'

    attr.setdefault('alt', default_text)
    attr.setdefault('title', default_text)

    return pokedex_img(pokemon_media_path(pokemon_species, prefix, ext),
                       **attr)
%></%def>

<%def name="pokemon_form_image(pokemon_form, prefix=None, **attr)"><%
    """Returns an <img> tag for a Pokémon form image."""

    if prefix is None:
        prefix = 'main-sprites/ultra-sun-ultra-moon'
        # FIXME what the hell is going on here
        if not pokemon_has_media(pokemon_form, prefix, 'png'):
            prefix = 'main-sprites/black-white'

        # Deal with Spiky-eared Pichu and ??? Arceus
        if pokemon_form.pokemon_form_generations:
            last_gen = pokemon_form.pokemon_form_generations[-1].generation_id
            if last_gen == 4:
                prefix = 'main-sprites/heartgold-soulsilver'

    default_text = pokemon_form.name

    if 'animated' in prefix:
        ext = 'gif'
    elif 'dream-world' in prefix:
        ext = 'svg'
    else:
        ext = 'png'

    attr.setdefault('alt', default_text)
    attr.setdefault('title', default_text)

    return pokedex_img(pokemon_media_path(pokemon_form.species, prefix, ext, form=pokemon_form),
                       **attr)
%></%def>

<%def name="pokemon_icon(pokemon, alt=True)"><%
    if pokemon.is_default:
        return h.literal('<span class="sprite-icon sprite-icon-%d"></span>' % pokemon.species.id)

    alt_text = pokemon.name if alt else u''
    if pokemon_has_media(pokemon.default_form, 'icons', 'png'):
        return pokemon_form_image(pokemon.default_form, prefix='icons', alt=alt_text)

    return pokedex_img('pokemon/icons/0.png', title=pokemon.species.name, alt=alt_text)
%></%def>

<%def name="pokemon_link(pokemon, content=None, **attr)"><%
    """Returns a link to a Pokémon page.

    `pokemon`
        A Pokemon object.

    `content`
        Link text (or image, or whatever).
    """

    # Content defaults to the name of the Pokémon
    if not content:
        content = pokemon.name

    url_kwargs = {}
    if pokemon.default_form.form_identifier:
        # Don't want a ?form=None, or a ?form=default
        url_kwargs['form'] = pokemon.default_form.form_identifier

    return h.HTML.a(
        content,
        href=url(controller='dex', action='pokemon',
                       name=pokemon.species.name.lower(), **url_kwargs),
        **attr
        )
%></%def>

<%def name="form_flavor_link(form, content=None, **attr)"><%
    """Returns a link to a pokemon form's flavor page.

    `form`
        A PokemonForm object.

    `content`
        Link text (or image, or whatever).
    """
    if not content:
        content = form.name

    url_kwargs = {}
    if form.form_identifier:
        # Don't want a ?form=None, or a ?form=default
        url_kwargs['form'] = form.form_identifier

    return h.HTML.a(
        content,
        href=url(controller='dex', action='pokemon_flavor',
                       name=form.species.name.lower(), **url_kwargs),
        **attr
        )
%></%def>

<%def name="damage_class_icon(damage_class)"><%
    return pokedex_img(
        "damage-classes/%s.png" % damage_class.identifier,
        alt=damage_class.name,
        title=_("%s: %s", context="damage class: description") % (
                damage_class.name.capitalize(),
                damage_class.description,
            )
    )
%></%def>


<%def name="type_icon(type)"><%
    if isinstance(type, basestring):
        if type == '???':
            identifier = 'unknown'
        else:
            identifier = type.lower()
        name = type
    else:
        name = type.name
        identifier = type.identifier
    return pokedex_img('types/{1}/{0}.png'.format(identifier, c.game_language.identifier),
            alt=name, title=name)
%></%def>

<%def name="type_link(type)"><%
    return h.HTML.a(
        type_icon(type),
        href=url(controller='dex', action='types', name=type.identifier),
    )
%></%def>

<%def name="item_filename(item)"><%
    if item.pocket.identifier == u'machines':
        machines = item.machines
        prefix = u'hm' if machines[-1].is_hm else u'tm'
        filename = prefix + u'-' + machines[-1].move.type.identifier
    elif item.identifier.startswith(u'data-card-'):
        filename = u'data-card'
    else:
        filename = item.identifier

    return filename
%></%def>

<%def name="item_link(item, include_icon=True)"><%
    """Returns a link to the requested item."""

    item_name = item.name

    if include_icon:
        label = pokedex_img("items/%s.png" % item_filename(item),
            alt=item_name, title=item_name) + ' ' + item_name
    else:
        label = item_name

    return h.HTML.a(label,
        href=url(controller='dex', action='items',
                 pocket=item.pocket.identifier, name=item_name.lower()),
    )
%></%def>

<%def name="pokemon_page_header(icon_form=None, subpages=True)">
<div id="dex-header">
    <a href="${url.current(name=c.prev_species.name.lower(), form=None)}" id="dex-header-prev" class="dex-box-link">
        <img src="${h.static_uri('spline', 'icons/control-180.png')}" alt="«">
        ${pokemon_icon(c.prev_species.default_pokemon, alt="")}
        ${c.prev_species.id}: ${c.prev_species.name}
    </a>
    <a href="${url.current(name=c.next_species.name.lower(), form=None)}" id="dex-header-next" class="dex-box-link">
        ${c.next_species.id}: ${c.next_species.name}
        ${pokemon_icon(c.next_species.default_pokemon, alt="")}
        <img src="${h.static_uri('spline', 'icons/control.png')}" alt="»">
    </a>
    ${pokemon_form_image(icon_form or c.pokemon.default_form, prefix='icons')}
    <br>${c.pokemon.species.id}: ${c.pokemon.species.name}
    % if subpages:
        <ul class="inline-menu">
        <% form = c.pokemon.default_form.form_identifier if not c.pokemon.is_default else None %>\
        % for action, label in (('pokemon', u'Pokédex'), \
                                ('pokemon_flavor', u'Flavor'), \
                                ('pokemon_locations', u'Locations')):
            % if action == request.environ['pylons.routes_dict']['action']:
            <li>${label}</li>
            % else:
            <li><a href="${url.current(action=action, form=form if action != 'pokemon_locations' else None)}">${label}</a></li>
            % endif
        % endfor
        % if c.pokemon.species.conquest_order is not None:
            <li><a href="${url(controller='dex_conquest', action='pokemon', name=c.pokemon.species.name.lower())}">Conquest</a></li>
        % endif
        </ul>
    % endif
</div>
</%def>


## Pretty-prints a version group selector, arranged by generation
<%def name="pretty_version_group_field(field, generations)">
<% version_group_controls = dict((control.data, control) for control in field) %>\
<table id="dex-pokemon-search-move-versions">
    % for generation in generations:
    <tr>
        % for version_group in generation.version_groups:
        <td>
            ${version_group_controls[ unicode(version_group.id) ]()}
            ${version_group_controls[ unicode(version_group.id) ].label()}
        </td>
        % endfor
    </tr>
    % endfor
</table>
% for error in field.errors:
<p class="error">${error}</p>
% endfor
</%def>


###### Common tables
<%def name="pokemon_move_table_column_header(column, move_method=None)">
<th class="version">
  % if len(column) == len(column[0].generation.version_groups):
    ## If the entire gen has been collapsed into a single column, just show
    ## the gen icon instead of the messy stack of version icons
    ${generation_icon(column[0].generation)}
  % else:
    <%
        if move_method:
            # Only select version groups that support this move method
            visible_version_groups = [vg for vg in column if
                vg in move_method.version_groups]
            # But if nothing is selected, put everything back
            if not visible_version_groups:
                visible_version_groups = column
        else:
            visible_version_groups = column
    %>
    % for i, version_group in enumerate(visible_version_groups):
    % if i != 0:
    <br>
    % endif
    ${version_group_icon(version_group)}
    % endfor
  % endif
</th>
</%def>


## Given a method and some data, returns a cell indicating in some useful
## manner how a move is learned.
## Makes some use of c.move_tutor_version_groups, if it exists.
## XXX How to sort these "correctly"...?
<%def name="pokemon_move_table_method_cell(column, method, version_group_data)">
% if method.identifier == u'tutor' and c.move_tutor_version_groups:
    <td class="tutored">
    ## Tutored moves never ever collapse!  Have to merge all the known values,
    ## rather than ignoring all but the first
    % for version_group in column:
        % if version_group in version_group_data:
        ${version_group_icon(version_group)}
        % elif version_group in c.move_tutor_version_groups:
        <span class="no-tutor">${version_group_icon(version_group)}</span>
        % endif
    % endfor
    </td>
% else:
    % for version_group in column:
        ## Display the first thing that's not empty (in that case the pokémon
        ## doesn't learn the move in this version_group, BUT could learn it in
        ## another one
        ## (e.g. Colosseum doesn't have egg moves but is grouped with Ruby)
        % if version_group not in version_group_data:
            <% continue %>
        % endif
        ## Otherwise display what we have
        % if method.identifier == u'level-up':
            <td>
            % if version_group_data[version_group]['level'] == 1:
                —
            % else:
                ${version_group_data[version_group]['level']}
            % endif
            </td>
        % elif method.identifier == u'machine':
            <% machine_number = version_group_data[version_group]['machine'] %>\
            <td>
            % if machine_number > 100:
            ## HM
                <strong>H</strong>${machine_number - 100}
            % else:
                ${"%02d" % machine_number}
            % endif
            </td>
        % elif method.identifier == u'egg':
            <td class="dex-moves-egg">${h.pokedex.chrome_img('egg-cropped.png',
                alt=h.literal(u"&bull;"))}</td>
        % else:
            <td>&bull;</td>
        % endif
        ## Don't try other version groups now that we've displayed something
        <% break %>
    % else:
        ## We didn't find any version group that has this move, so display an
        ## empty cell
        <td></td>
    % endfor
% endif
</%def>


<%def name="pokemon_table_columns()">
<col class="dex-col-icon">
<col class="dex-col-name">
<col class="dex-col-type2">
<col class="dex-col-ability">
<col class="dex-col-gender">
<col class="dex-col-egg-group">
<col class="dex-col-stat">
<col class="dex-col-stat">
<col class="dex-col-stat">
<col class="dex-col-stat">
<col class="dex-col-stat">
<col class="dex-col-stat">
<col class="dex-col-stat-total">
</%def>

<%def name="pokemon_table_header()">
<th></th>
<th>Pokémon</th>
<th>Type</th>
<th>Ability</th>
<th>Gender</th>
<th>Egg Group</th>
<th><abbr title="Hit Points">HP</abbr></th>
<th><abbr title="Attack">Atk</abbr></th>
<th><abbr title="Defense">Def</abbr></th>
<th><abbr title="Special Attack">SpA</abbr></th>
<th><abbr title="Special Defense">SpD</abbr></th>
<th><abbr title="Speed">Spd</abbr></th>
<th>Total</th>
</%def>

<%def name="_pokemon_ability_link(ability)">
<a href="${url(controller='dex', action='abilities', name=ability.name.lower())}">${ability.name}</a>
</%def>

<%def name="pokemon_table_row(pokemon)">
<td class="icon">${pokemon_icon(pokemon)}</td>
<td>${pokemon_link(pokemon)}</td>
<td class="type2">
    % for type in pokemon.types:
    ${type_link(type)}
    % endfor
</td>
<td class="ability">
  % for i, ability in enumerate(pokemon.abilities):
    % if i > 0:
    <br />
    % endif
    ${_pokemon_ability_link(ability)}
  % endfor
  % if pokemon.hidden_ability and pokemon.hidden_ability not in pokemon.abilities:
    <br />
    <em>${_pokemon_ability_link(pokemon.hidden_ability)}</em>
  % endif
</td>
<td>${chrome_img('gender-rates/%d.png' % pokemon.species.gender_rate, alt=h.pokedex.gender_rate_label[pokemon.species.gender_rate])}</td>
<td class="egg-group">
  % for i, egg_group in enumerate(pokemon.species.egg_groups):
    % if i > 0:
    <br>
    % endif
    ${egg_group.name}
  % endfor
</td>
% for stat_identifier in ['hp', 'attack', 'defense', 'special-attack', 'special-defense', 'speed']:
    <td class="stat stat-${stat_identifier}">${pokemon.base_stat(stat_identifier, '?')}</td>
% endfor
% if pokemon.stats:
    <td>${sum((pokemon_stat.base_stat for pokemon_stat in pokemon.stats))}</td>
% else:
    <td>?</td>
% endif
</%def>


<%def name="move_table_columns()">
<col class="dex-col-name">
<col class="dex-col-type">
<col class="dex-col-type">
<col class="dex-col-stat">
<col class="dex-col-stat">
<col class="dex-col-stat">
<col class="dex-col-stat">
<col class="dex-col-effect">
</%def>

<%def name="move_table_header(gen_instead_of_type=False)">
<th>Move</th>
% if gen_instead_of_type:
<th>Gen</th>
% else:
<th>Type</th>
% endif
<th>Class</th>
<th>PP</th>
<th>Power</th>
<th>Acc</th>
<th>Pri</th>
<th>Effect</th>
</%def>

<%def name="move_table_row(move, gen_instead_of_type=False, pp_override=None)">
<td><a href="${url(controller='dex', action='moves', name=move.name.lower())}">${move.name}</a></td>
% if gen_instead_of_type:
## Done on type pages; we already know the type, so show the generation instead
<td class="type">${generation_icon(move.generation)}</td>
% else:
<td class="type">${type_link(move.type)}</td>
% endif
<td class="class">${damage_class_icon(move.damage_class)}</td>
<td>
    % if pp_override and pp_override != move.pp:
    <s>${move.pp}</s> <br> ${pp_override}
    % else:
    ${move.pp or u'—'}
    % endif
</td>
<td>
    % if move.power is not None:
    ${move.power}
    % elif move.damage_class.identifier == 'status':
    —
    % else:
    *
    % endif
</td>
<td>
    % if move.accuracy is None:
    —
    % else:
    ${move.accuracy}%
    % endif
</td>
## Priority is colored red for slow and green for fast
% if move.priority == 0:
<td></td>
% elif move.priority > 0:
<td class="dex-priority-fast">${move.priority}</td>
% else:
<td class="dex-priority-slow">${move.priority}</td>
% endif
<td class="markdown effect">${move.short_effect}</td>
</%def>

<%def name="move_table_blank_row()">
<td>&mdash;</td>
<td colspan="7"></td>
</%def>

###### Miscellaneous flavour presentation

<%def name="flavor_text_list(flavor_text, classes='')">
<%
flavor_text = (text for text in flavor_text if text.language == c.game_language)
obdurate = session.get('cheat_obdurate', False)
collapse_key = h.pokedex.collapse_flavor_text_key(literal=obdurate)
%>
<dl class="dex-flavor-text${' ' if classes else ''}${classes}">
% for generation, group in h.pokedex.group_by_generation(flavor_text):
<dt class="dex-flavor-generation">${h.pokedex.generation_icon(generation)}</dt>
<dd>
  <dl>
  % for versions, text in h.pokedex.collapse_versions(group, key=collapse_key):
    <dt>${h.pokedex.version_icons(*versions)}</dt>
    <dd><p${' class="dex-obdurate"' if obdurate else '' |n}>${text}</p></dd>
  % endfor
  </dl>
</dd>
% endfor
</dl>
</%def>

<%def name="pokemon_cry(pokemon_form)">
<%
species = pokemon_form.species

# A handful of Pokémon have separate cries for each form; most don't
if not pokemon_has_media(pokemon_form, 'cries', 'ogg'):
    pokemon_form = None

cry_url = url(controller='dex', action='media',
    path=pokemon_media_path(species, 'cries', 'ogg', pokemon_form))
%>
<audio src="${cry_url}" controls preload="auto" class="cry">
    <!-- Totally the best fallback -->
    <a href="${cry_url}">${_('Download')}</a>
</audio>
</%def>

<%def name="subtle_search(**kwargs)">
    <% _ = kwargs.pop('_', unicode) %>
    <a href="${url(controller='dex_search', **kwargs)}"
        class="dex-subtle-search-link">
        <img src="${h.static_uri('spline', 'icons/magnifier-small.png')}" alt="${_('Search: ')}" title="${_('Search')}">
    </a>
</%def>

<%def name="foreign_names(object, name_attr='name')">
    <dl>
        % for language, foreign_name in h.keysort(getattr(object, name_attr + '_map'), lambda lang: lang.order):
        % if language != c.game_language and foreign_name:
        ## </dt> needs to come right after the flag or else there's space between it and the colon
        <dt>${language.name}
        <img src="${h.static_uri('spline', "flags/{0}.png".format(language.iso3166))}" alt=""></dt>
        % if language.identifier == 'ja-Hrkt':
        <dd>${foreign_name} (${h.pokedex.romanize(foreign_name)})</dd>
        % else:
        <dd>${foreign_name}</dd>
        % endif
        % endif
        % endfor
    </dl>
</%def>
