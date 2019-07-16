from pyramid.renderers import render_to_response
from pyramid.response import Response

def notfound(request, table, name):
    """Returns a 404 response for a missing resource.

    Same as the generic 404 handler (pyramidapp.error_view) for now,
    but might change to a more helpful response in the future.
    """
    c = request.tmpl_context
    c.code = 404
    c.message = u"404 Not Found"
    response = Response(status=404)
    return render_to_response('error.mako', {}, request=request, response=response)
