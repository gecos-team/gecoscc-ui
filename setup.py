import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()
CHANGES = open(os.path.join(here, 'CHANGES.txt')).read()

requires = [
    'pyramid>=1.4',
    'pyramid_jinja2',
    'pyramid_debugtoolbar',
    'pyramid_beaker==0.7',
    'pyramid_tm==0.7',
    'colander==1.0b1',
    'Babel==1.3',
    'lingua==1.5',
    'pymongo==2.6.3',
    'py-bcrypt==0.4',
    'gunicorn==18.0',
    'pyramid_sockjs==0.3.9',
    'celery==3.0.24',
    'celery-with-mongodb==3.0',
    'pyramid_celery==1.3',
    'cornice==0.16.2',
    'jsonschema==2.3.0',

    'gevent-websocket==0.3.6',
]

setup(name='gecoscc',
      version='0.2.1',
      description='gecoscc',
      long_description=README + '\n\n' + CHANGES,
      classifiers=[
          "Programming Language :: Python",
          "Framework :: Pylons",
          "Topic :: Internet :: WWW/HTTP",
          "Topic :: Internet :: WWW/HTTP :: WSGI :: Application",
      ],
      author='Junta de Andalucia',
      author_email='',
      url='https://github.com/gecos-team',
      keywords='web pyramid pylons',
      packages=find_packages(),
      include_package_data=True,
      zip_safe=False,
      package_data={
          'templates': ['*.jinja2'],
          'locale': ['*.pot', '*.po', '*.mo'],
          'static': ['*.js', '*.css', '*.jpg', '*.png'],
      },
      install_requires=requires,
      tests_require=requires,
      test_suite="gecoscc",
      entry_points="""\
      [paste.app_factory]
      main = gecoscc:main
      [console_scripts]
      pmanage = gecoscc.management:main
      [gecoscc.policies]
      remotestorage = gecoscc.policies.remotestorage:Policy
      """,
      paster_plugins=['pyramid'],
      )
