# encoding: utf8

class NullTranslator(object):
    """Looks like a Translator, quacks like a Translator, but doesn't actually
    translate
    """
    def __init__(*stuff, **more_stuff):
        pass

    def __call__(self, message, *stuff, **more_stuff):
        return handle_template(message)

class Translator(BaseTranslator):
    package = 'splinext.pokedex'
    domain = 'spline-pokedex'
