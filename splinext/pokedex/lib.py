from collections import OrderedDict
from datetime import datetime, timedelta

from .i18n import NullTranslator


class Link(object):
    """Represents a link in the header bar."""

    def __init__(self, label, route_name=None, children=[], collapsed=False, translator_class=NullTranslator, i18n_context=None):
        """Arguments:
        `label`
            Label for this link.
        `route_name`
            Name of the route to link to.  If omitted, this link may serve as
            merely a header instead.
        `children`
            An optional list of PluginLink objects.
        `collapsed`
            Whether this link appears on the menu.  It will still appear in a
            table of contents.
        `translator`
            A class used to translate the label. Will be instantiated.
        `i18n_context`
            I18n context, passed to the translator
        """

        self.label = label
        self.route_name = route_name
        self.children = children
        self.collapsed = collapsed
        self.translator_class = translator_class
        self.i18n_context = i18n_context

        # Make this tree bidirectional
        self.parent = None
        for child in children:
            child.parent = self

    def url(self, request):
        # TODO: translation?
        if self.route_name:
            if self.route_name.startswith('/'):
                return self.route_name # XXX
            else:
                return request.route_path(self.route_name)
        return '/unknown'


class ResponseTimer(object):
    """Nearly trivial class, used for tracking how long the page took to create.
    Properties are `total_time`, `sql_time`, and `sql_queries`.
    In SQL debug mode, `sql_query_log` is also populated.  Its keys are
    queries; values are dicts of parameters, time, and caller.
    """

    def __init__(self):
        self._start_time = datetime.now()
        self._total_time = None

        self.from_cache = None

        # SQLAlchemy will add to these using the above event listeners; see
        # spline.config.environment
        self.sql_time = timedelta()
        self.sql_queries = 0
        self.sql_query_log = OrderedDict()

    @property
    def total_time(self):
        # Calculate and save the total render time as soon as this is accessed
        if self._total_time is None:
            self._total_time = datetime.now() - self._start_time
        return self._total_time

    def add_log(self, log):
        self.sql_query_log.setdefault(log['statement'], []).append(log)

