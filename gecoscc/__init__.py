import os

from pyramid.config import Configurator
from pyramid.exceptions import ConfigurationError
from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy

from gecoscc.db import MongoDB, get_db
from gecoscc.models import get_root
from gecoscc.userdb import get_userdb, get_groups, get_user
from gecoscc.eventsmanager import EventsManager


def read_setting_from_env(settings, key, default=None):
    env_variable = key.upper()
    if env_variable in os.environ:
        return os.environ[env_variable]
    else:
        return settings.get(key, default)


def route_config(config):
    config.add_static_view('static', 'static')
    config.add_route('home', '/')
    config.add_route('login', '/login/')
    config.add_route('logout', '/logout/')
    config.add_route('message', '/message/')
    config.add_sockjs_route('sockjs', prefix='/sockjs',
                            session=EventsManager,
                            per_user=True,
                            cookie_needed=True)


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
    config.add_request_method(get_user, 'user', reify=True)


def auth_config(config):
    settings = config.registry.settings
    secret = read_setting_from_env(settings, 'session.secret', None)

    authn_policy = AuthTktAuthenticationPolicy(
        secret, callback=get_groups, hashalg='sha512')
    authz_policy = ACLAuthorizationPolicy()
    config.set_authentication_policy(authn_policy)
    config.set_authorization_policy(authz_policy)


def jinja2_config(config):
    settings = config.registry.settings
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

    database_config(config)
    userdb_config(config)
    auth_config(config)

    config.add_translation_dirs('locale/')

    jinja2_config(config)

    config.include('pyramid_jinja2')
    config.include('pyramid_beaker')
    config.include('pyramid_sockjs')

    route_config(config)

    config.scan('gecoscc.views')

    return config.make_wsgi_app()
