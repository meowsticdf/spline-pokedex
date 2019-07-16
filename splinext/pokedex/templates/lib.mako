<%def name="cache_content()"><%
    # _cache_me is set by viewlib.cache_content
    c._cache_me(context, caller)
%></%def>

<%def name="field(name, form=None, **render_args)">
<% form = form or c.form %>\
    <dt>${form[name].label() | n}</dt>
    <dd>${form[name](id=u'', **render_args) | n}</dd>
    % for error in form[name].errors:
    <dd class="error">${error}</dd>
    % endfor
</%def>

<%def name="bare_field(name, form=None, **render_args)">
<% form = form or c.form %>\
    ${form[name](id=u'', **render_args) | n}
    % for error in form[name].errors:
    <p class="error">${error}</p>
    % endfor
</%def>

<%def name="literal_field(field, **render_args)">
    ${field(id=u'', **render_args) | n}
    % for error in field.errors:
    <p class="error">${error}</p>
    % endfor
</%def>

<%def name="escape_html()" filter="h">${caller.body()}</%def>
