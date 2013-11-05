import os

from pyramid.config import Configurator
from pyramid.exceptions import ConfigurationError

from gecoscc.db import MongoDB, get_db
from gecoscc.models import get_root
from gecoscc.userdb import get_userdb


def read_setting_from_env(settings, key, default=None):
    env_variable = key.upper()
    if env_variable in os.environ:
        return os.environ[env_variable]
    else:
        return settings.get(key, default)


def route_config(config):
    config.add_static_view('static', 'static')
    config.add_view('gecoscc.views.my_view',
                    context='gecoscc.models.MyModel',
                    renderer="mytemplate.jinja2")


def database_config(config):

    settings = config.registry.settings
    mongo_uri = read_setting_from_env(settings, 'mongo_uri', None)
    if not mongo_uri:
        raise ConfigurationError("The mongo_uri option is required")

    settings['mongo_uri'] = mongo_uri

    mongo_replicaset = read_setting_from_env(settings, 'mongo_replicaset',
                                             None)
    settings['mongo_replicaset'] = mongo_replicaset

    if mongo_replicaset is not None:
        mongodb = MongoDB(settings['mongo_uri'],
                          replicaSet=mongo_replicaset)
    else:
        mongodb = MongoDB(settings['mongo_uri'])
    config.registry.settings['mongodb'] = mongodb
    config.registry.settings['db_conn'] = mongodb.get_connection()

    config.set_request_property(get_db, 'db', reify=True)


def userdb_config(config):
    # TODO
    # * Support LDAP Users
    # * Organization Users
    # * Mixed users
    from .userdb import MongoUserDB

    userdb = MongoUserDB(config.registry.settings['mongodb'], 'adminusers')
    config.registry.settings['userdb'] = userdb
    config.set_request_property(get_userdb, 'userdb', reify=True)


def jinja2_settings(settings):
    settings.setdefault('jinja2.i18n.domain', 'gecoscc')
    settings.setdefault('jinja2.newstyle', True)

    settings.setdefault('jinja2.extensions', ['jinja2.ext.with_'])

    settings.setdefault('jinja2.directories', 'gecoscc:templates')
    settings.setdefault('jinja2.undefined', 'strict')
    settings.setdefault('jinja2.filters', """
        route_url = pyramid_jinja2.filters:route_url_filter
        static_url = pyramid_jinja2.filters:static_url_filter
    """)


def main(global_config, **settings):
    """ This function returns a WSGI application.
    """
    settings = dict(settings)

    config = Configurator(root_factory=get_root, settings=settings)
    config.add_translation_dirs('locale/')
    config.include('pyramid_jinja2')

    jinja2_settings(settings)

    database_config(config)
    userdb_config(config)
    route_config(config)

    return config.make_wsgi_app()
