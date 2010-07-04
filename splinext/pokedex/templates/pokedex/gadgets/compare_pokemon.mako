<%inherit file="/base.mako" />

<%def name="title()">Compare Pokémon</%def>

<%def name="title_in_page()">
<ul id="breadcrumbs">
    <li><a href="${url('/dex')}">Pokédex</a></li>
    <li>Gadgets</li>
    <li>Compare Pokémon</li>
</ul>
</%def>

<h1>Compare Pokémon</h1>
<p>Select up to eight Pokémon to compare their stats, moves, etc.</p>

${h.form(url.current(), method='GET')}
<table class="dex-compare-pokemon">
<col class="labels">
<thead>
    % if c.did_anything and any(_ and _.suggestions for _ in c.found_pokemon):
    <tr class="dex-compare-suggestions">
        <th><!-- label column --></th>
        % for found_pokemon in c.found_pokemon:
        <th>
            % if found_pokemon is None or found_pokemon.suggestions is None:
            <% pass %>\
            % elif found_pokemon.pokemon is None:
            no matches
            % else:
            <ul>
                % for suggestion, iso3166 in found_pokemon.suggestions:
                <li><a href="${c.create_comparison_link(target=found_pokemon, replace_with=suggestion)}">
                    % if iso3166:
                    <img src="${h.static_uri('spline', "flags/{0}.png".format(iso3166))}" alt="">
                    % endif
                    ${suggestion}?
                </a></li>
                % endfor
            </ul>
            % endif
        </th>
        % endfor
    </tr>
    % endif
    <tr class="header-row">
        <th><button type="submit">Compare:</button></th>
        % for found_pokemon in c.found_pokemon:
        <th>
            % if found_pokemon and found_pokemon.pokemon:
            ${h.pokedex.pokemon_link(found_pokemon.pokemon,
                h.pokedex.pokemon_sprite(found_pokemon.pokemon, prefix=u'icons'),
                class_='dex-box-link',
            )}<br>
            % endif
            <input type="text" name="pokemon" value="${found_pokemon.input if found_pokemon else u''}">
        </th>
        % endfor
    </tr>
    % if c.did_anything:
    <tr class="subheader-row">
        <th><!-- label column --></th>
        % for found_pokemon in c.found_pokemon:
        <th>
            <a href="${c.create_comparison_link(target=found_pokemon, move=-1)}">
                <img src="${h.static_uri('spline', 'icons/arrow-180-small.png')}" alt="←" title="Move left">
            </a>
            <a href="${c.create_comparison_link(target=found_pokemon, replace_with=u'')}">
                <img src="${h.static_uri('spline', 'icons/cross-small.png')}" alt="remove" title="Remove">
            </a>
            <a href="${c.create_comparison_link(target=found_pokemon, move=+1)}">
                <img src="${h.static_uri('spline', 'icons/arrow-000-small.png')}" alt="→" title="Move right">
            </a>
        </th>
        % endfor
    </tr>
    % endif
</thead>
</table>
${h.end_form()}

% if c.did_anything:
<table class="striped-rows dex-compare-pokemon">
<col class="labels">
<tbody>
    ${row(u'Type', type_cell)}
    ${row(u'Abilities', abilities_cell)}

    <tr class="subheader-row">
        <th colspan="${len(c.found_pokemon) + 1}">Breeding + Training</th>
    </tr>
    ${row(u'Egg groups', egg_groups_cell)}
    ${row(u'Gender', gender_cell)}
    ${row(u'Base EXP', base_exp_cell)}
    ${row(u'Base happiness', base_happiness_cell)}
    ${row(u'Capture rate', capture_rate_cell)}

    <tr class="subheader-row">
        <th colspan="${len(c.found_pokemon) + 1}">Stats</th>
    </tr>
    % for stat in c.stats:
    ${row(stat.name, stat_cell, stat)}
    % endfor
    ${row(u'Effort', effort_cell)}

    <tr class="subheader-row">
        <th colspan="${len(c.found_pokemon) + 1}">Flavor</th>
    </tr>
    ${row(u'Height', height_cell)}
    ${row(u'Weight', weight_cell)}
</tbody>
</table>
% endif  ## did anything


## Column headers for a new table
<%def name="table_header()">
<thead>
    <tr class="header-row">
        <th><!-- label column --></th>
        % for found_pokemon in c.found_pokemon:
        <th>
            % if found_pokemon and found_pokemon.pokemon:
            ${h.pokedex.pokemon_link(found_pokemon.pokemon,
                h.pokedex.pokemon_sprite(found_pokemon.pokemon, prefix=u'icons')
                + h.literal('<br>')
                + found_pokemon.pokemon.full_name)}
            % endif
        </th>
        % endfor
    </tr>
</thead>
</%def>

## Print a row of 8
<%def name="row(label, cell_func, *args, **kwargs)">
    <tr>
        <th>${label}</th>
        % for found_pokemon in c.found_pokemon:
        <td>
            % if found_pokemon and found_pokemon.pokemon:
            ${cell_func(found_pokemon.pokemon, *args, **kwargs)}
            % endif
        </td>
        % endfor
    </tr>
</%def>

## Cells
<%def name="type_cell(pokemon)">
<ul>
    % for type in pokemon.types:
    <li>${h.pokedex.type_link(type)}</li>
    % endfor
</ul>
</%def>

<%def name="abilities_cell(pokemon)">
<ul>
    % for ability in pokemon.abilities:
    <li><a href="${url(controller='dex', action='abilities', name=ability.name.lower())}">${ability.name}</a></li>
    % endfor
</ul>
</%def>

<%def name="egg_groups_cell(pokemon)">
<ul>
    % for egg_group in pokemon.egg_groups:
    <li>${egg_group.name}</li>
    % endfor
</ul>
</%def>

<%def name="gender_cell(pokemon)">
${h.pokedex.pokedex_img('gender-rates/%d.png' % pokemon.gender_rate, alt='')}<br>
${h.pokedex.gender_rate_label[pokemon.gender_rate]}
</%def>

<%def name="base_exp_cell(pokemon)">${pokemon.base_experience}</%def>

<%def name="base_happiness_cell(pokemon)">${pokemon.base_happiness}</%def>

<%def name="capture_rate_cell(pokemon)">${pokemon.capture_rate}</%def>

<%def name="stat_cell(pokemon, stat)">${pokemon.stat(stat).base_stat}</%def>

<%def name="effort_cell(pokemon)">
<ul>
    % for stat in c.stats:
    <% effort = pokemon.stat(stat).effort %>\
    <li>
        % if effort:
        ${effort} ${stat.name}
        % else:
        &nbsp;
        % endif
    </li>
    % endfor
</ul>
</%def>

<%def name="height_cell(pokemon)">${h.pokedex.format_height_imperial(pokemon.height)}</%def>
<%def name="weight_cell(pokemon)">${h.pokedex.format_weight_imperial(pokemon.weight)}</%def>
