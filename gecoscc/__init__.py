import os
import pymongo

from pyramid.config import Configurator
from pyramid.exceptions import ConfigurationError
from pyramid.authentication import AuthTktAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy

from gecoscc.db import MongoDB, get_db
from gecoscc.models import get_root
from gecoscc.userdb import get_userdb, get_groups, get_user
from gecoscc.eventsmanager import EventsManager
from gecoscc.permissions import is_logged


def read_setting_from_env(settings, key, default=None):
    env_variable = key.upper()
    if env_variable in os.environ:
        return os.environ[env_variable]
    else:
        return settings.get(key, default)


def route_config(config):
    config.add_static_view('static', 'static')
    config.add_route('home', '/')
    config.add_route('admins', '/admins/')
    config.add_route('groups', '/groups/')
    config.add_route('reports', '/reports/')
    config.add_route('login', '/login/')
    config.add_route('logout', 'logout/')
    config.add_sockjs_route('sockjs', prefix='/sockjs',
                            session=EventsManager,
                            per_user=True,
                            cookie_needed=True)


def route_config_auxiliary(config, route_prefix):
    config.add_route('sockjs_home', route_prefix)
    config.add_route('sockjs_message', '%smessage/' % route_prefix)


def to_delete_route_config(config):
    config.add_route('users', '/users/')
    config.add_route('ous', '/ous/')
    config.add_route('policies_wallpaper', '/ous/policies-wallpaper/')
    config.add_route('policies_software', '/ous/policies-software/')
    config.add_route('policies_storage', '/ous/policies-storage/')
    config.add_route('computers', '/computers/')
    config.add_route('printers', '/printers/')


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


def celery_config(config):
    settings = config.registry.settings
    settings['CELERY_IMPORTS'] = ('gecoscc.tasks', )
    if not settings.get('BROKER_URL', ''):

        parsed_uri = pymongo.uri_parser.parse_uri(settings['mongo_uri'])

        settings['BROKER_URL'] = settings['mongo_uri']
        settings['CELERY_RESULT_BACKEND'] = "mongodb"
        settings['CELERY_MONGODB_BACKEND_SETTINGS'] = {
            "host": parsed_uri.get('nodelist')[0][0],
            "port": parsed_uri.get('nodelist')[0][1],
            "database": parsed_uri.get('database'),
            "taskmeta_collection": "celery_taskmeta",
        }
        if parsed_uri.get('username', ''):
            settings['CELERY_MONGODB_BACKEND_SETTINGS'].update({
                "user": parsed_uri.get('username'),
                "password": parsed_uri.get("password"),
            })
        if parsed_uri.get('options', ''):
            settings['CELERY_MONGODB_BACKEND_SETTINGS'].update({
                "options": parsed_uri.get('options'),
            })


def main(global_config, **settings):
    """ This function returns a WSGI application.
    """
    settings = dict(settings)

    config = Configurator(root_factory=get_root, settings=settings)

    database_config(config)
    userdb_config(config)
    auth_config(config)
    celery_config(config)

    config.add_translation_dirs('locale/')

    jinja2_config(config)

    config.include('pyramid_jinja2')
    config.include('pyramid_beaker')
    config.include('pyramid_sockjs')
    config.include('pyramid_celery')
    config.include('cornice')

    route_config(config)
    to_delete_route_config(config)
    route_config_auxiliary(config, route_prefix='/sjs/')

    config.set_request_property(is_logged, 'is_logged', reify=True)

    config.scan('gecoscc.views')
    config.scan('gecoscc.api')

    return config.make_wsgi_app()
