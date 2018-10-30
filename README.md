<strike>spline-pokedex</strike> pyramid_pokedex
----

This is an experimental attempt to port spline-pokedex to pyramid.
For more info see <https://github.com/veekun/spline-pokedex/issues/115>.

### Quickstart instructions:

Assuming you have a virtualenv with [pokedex][] already installed.

[pokedex]: http://github.com/veekun/pokedex/

1. `pip install -e .`
2. `cd veekun`
3. copy pyramid.ini_tmpl to pyramid.ini and edit to your liking. 
   you should probably set beaker.session.secret and app_instance_uuid, although it probably doesn't matter.
4. `mkdir data && pokedex reindex -e postgresql:///yourdb -i data/pokedex-index`
5. `pserve --reload pyramid.ini`

