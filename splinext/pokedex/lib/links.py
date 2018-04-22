from spline.i18n import NullTranslator
class Link(object):
    """Represents a link in the header bar."""

    def __init__(self, label, url=None, children=[], collapsed=False, translator_class=NullTranslator, i18n_context=None):
        """Arguments:

        `label`
            Label for this link.

        `url`
            URL for this link.  If omitted, this link may serve as merely a
            header instead.

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
        self._url = url
        self.children = children
        self.collapsed = collapsed
        self.translator_class = translator_class
        self.i18n_context = i18n_context

        # Make this tree bidirectional
        self.parent = None
        for child in children:
            child.parent = self

    @property
    def url(self):
        # TODO: translation?
        return self._url
