from setuptools import setup, find_packages
setup(
    name = 'spline-pokedex',
    version = '0.2',
    packages = find_packages(),

    install_requires = [
        "pyramid>=1.5",
        "pyramid_beaker",
        "pyramid_debugtoolbar>=0.15.1",
        "pyramid_mako>=1.0.2",
        "pyramid_tm",
        "Mako>=0.3.4",
        "nose>=0.11",
        "WTForms>=1.0",
        "markdown",
        "webhelpers>=1.2",
        "waitress>=1.1.0", # development server
        #"Babel>=0.9.5", # needed for translation work only, can do without

        'pokedex',
        'SQLAlchemy>=0.7.5,<1.2.0b1',
        'zope.sqlalchemy',
        #'psycopg2-binary', # for postgresql support
    ],

    include_package_data = True,
    package_data={'splinext': ['*/i18n/*/LC_MESSAGES/*.mo']},

    zip_safe = False,
    test_suite='nose.collector',

    entry_points="""
    [babel.extractors]
    spline-python = spline.babelplugin:extract_python
    spline-mako = spline.babelplugin:extract_mako

    #[nose.plugins]
    #pylons = pylons.test:PylonsPlugin
    """,

    message_extractors = {'splinext': [
        ('**.py', 'spline-python', None),
        ('*/templates/**.mako', 'spline-mako', {'input_encoding': 'utf-8'}),
        ('*/content/**.html', 'spline-mako', {'input_encoding': 'utf-8'})]},
)
