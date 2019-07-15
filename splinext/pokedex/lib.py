from collections import OrderedDict
from datetime import datetime, timedelta

from webhelpers.html import escape

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
        #return '/unknown'
        return None


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


# Flash message implementation.

# Based on webhelpers.pylonslib.flash from WebHelpers 1.2, except that they
# needlessly restricted the metadata for a single flash message, and working
# around it was horrifically ugly.

class Message(object):
    """A message returned by ``Flash.pop_messages()``.

    Converting the message to a string returns the message text. Instances
    also have the following attributes:

    * ``message``: the message text.
    * ``category``: the category specified when the message was created.
    * ``icon``: the icon to show along with the message.
    """

    def __init__(self, category, message, icon):
        self.category = category
        self.message = message
        self.icon = icon

    def __str__(self):
        return self.message

    __unicode__ = __str__

    def __html__(self):
        return escape(self.message)


class Flash(object):
    """Accumulate a list of messages to show at the next page request.
    """

    # List of allowed categories.  If None, allow any category.
    categories = ["warning", "notice", "error", "success"]

    # Default category if none is specified.
    default_category = "notice"

    # Mapping of categories to icons.
    default_icons = dict(
        warning='exclamation-frame',
        notice='balloon-white',
        error='cross-circle',
        success='tick',
    )

    def __init__(self, session, session_key="flash", categories=None, default_category=None):
        """Instantiate a ``Flash`` object.

        ``session`` is the session object.

        ``session_key`` is the key to save the messages under in the user's
        session.

        ``categories`` is an optional list which overrides the default list
        of categories.

        ``default_category`` overrides the default category used for messages
        when none is specified.
        """
        self.session = session
        self.session_key = session_key
        if categories is not None:
            self.categories = categories
        if default_category is not None:
            self.default_category = default_category
        if self.categories and self.default_category not in self.categories:
            raise ValueError("unrecognized default category %r" % (self.default_category,))

    def __call__(self, message, category=None, icon=None, ignore_duplicate=False):
        """Add a message to the session.

        ``message`` is the message text.

        ``category`` is the message's category. If not specified, the default
        category will be used.  Raise ``ValueError`` if the category is not
        in the list of allowed categories.

        ``icon`` is the icon -- a filename from the Fugue icon set, without the
        file extension.

        If ``ignore_duplicate`` is true, don't add the message if another
        message with identical text has already been added. If the new
        message has a different category than the original message, change the
        original message to the new category.
        """

        if not category:
            category = self.default_category
        elif self.categories and category not in self.categories:
            raise ValueError("unrecognized category %r" % (category,))

        if not icon:
            icon = self.default_icons[category]

        # Don't store Message objects in the session, to avoid unpickling
        # errors in edge cases.
        new_message_dict = dict(message=message, category=category, icon=icon)
        messages = self.session.setdefault(self.session_key, [])
        # ``messages`` is a mutable list, so changes to the local variable are
        # reflected in the session.
        if ignore_duplicate:
            for i, m in enumerate(messages):
                if m['message'] == message:
                    if m['category'] != category or m['icon'] != icon:
                        messages[i] = new_message_dict
                        self.session.save()
                    return    # Original message found, so exit early.

        messages.append(new_message_dict)
        self.session.save()

    def pop_messages(self):
        """Return all accumulated messages and delete them from the session.

        The return value is a list of ``Message`` objects.
        """
        # pyramid_beaker automatically saves the session when a mutating method
        # like pop() is called. we don't want to save the session if we don't
        # have to (because doing so sets a cookie), so be careful not to call
        # pop unless there is actully data in the session
        if not self.session.get(self.session_key, []):
            return []

        messages = self.session.pop(self.session_key, [])
        self.session.save()
        return [Message(**m) for m in messages]
