import os

from setuptools import setup, find_packages

here = os.path.abspath(os.path.dirname(__file__))
README = open(os.path.join(here, 'README.rst')).read()
#CHANGES = open(os.path.join(here, 'CHANGES.txt')).read()

requires = open(os.path.join(here, 'requirements.txt')).read().splitlines()
test_requires = open(os.path.join(here, 'test_requirements.txt')).read().splitlines()

def get_version():
    with open('gecoscc/version.py') as f:
        for line in f:
            if line.startswith('__VERSION__'):
                return eval(line.split('=')[-1].strip())

setup(name='gecoscc',
      version=get_version(),
      description='gecoscc',
      long_description=README,
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
          'templates': ['*.jinja2', '*.html'],
          'locale': ['*.pot', '*.po', '*.mo'],
          'static': ['*.js', '*.css', '*.jpg', '*.png'],
      },
      install_requires=requires,
      tests_require=test_requires,
      test_suite="gecoscc",
      entry_points="""\
      [paste.app_factory]
      main = gecoscc:main
      [console_scripts]
      pmanage = gecoscc.management:main
      [gecoscc.policies]
      remote-storage = gecoscc.policies.remote_storage:RemoteStoragePolicy
      """,
      paster_plugins=['pyramid'],
      )
