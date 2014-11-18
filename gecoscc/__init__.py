import colander
import json
import os
import pymongo

from ConfigParser import ConfigParser

from pyramid.authentication import SessionAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.config import Configurator
from pyramid.exceptions import ConfigurationError
from pyramid.threadlocal import get_current_registry

from gecoscc.db import MongoDB, get_db
from gecoscc.models import get_root
from gecoscc.userdb import get_userdb, get_groups, get_user
from gecoscc.eventsmanager import get_jobstorage
from gecoscc.permissions import is_logged, LoggedFactory, SuperUserFactory, SuperUserOrMyProfileFactory
from gecoscc.socks import socketio_service


def read_setting_from_env(settings, key, default=None):
    env_variable = key.upper()
    if env_variable in os.environ:
        return os.environ[env_variable]
    else:
        return settings.get(key, default)


def route_config(config):
    config.add_static_view('static', 'static')
    config.add_route('home', '/', factory=LoggedFactory)
    config.add_route('admins', '/admins/', factory=SuperUserFactory)
    config.add_route('admins_add', '/admins/add/', factory=SuperUserFactory)
    config.add_route('admins_superuser', '/admins/superuser/{username}/', factory=SuperUserFactory)
    config.add_route('admins_ou_manage', '/admins/manage_ou/{username}/', factory=SuperUserFactory)

    config.add_route('admins_edit', '/admins/edit/{username}/', factory=SuperUserOrMyProfileFactory)
    config.add_route('admins_set_variables', '/admins/variables/{username}/', factory=SuperUserOrMyProfileFactory)
    config.add_route('admin_delete', '/admins/delete/', factory=SuperUserOrMyProfileFactory)

    config.add_route('reports', '/reports/', factory=SuperUserFactory)
    config.add_route('report_file', '/report/{report_type}/', factory=SuperUserFactory)
    config.add_route('i18n_catalog', '/i18n-catalog/')
    config.add_route('login', '/login/')
    config.add_route('logout', 'logout/')
    config.add_route('forbidden-view', '/error403/')
    config.add_renderer('csv', 'gecoscc.views.reports.CSVRenderer')


def sockjs_config(config, global_config):
    settings = config.registry.settings
    settings['redis.conf'] = json.loads(settings['redis.conf'])
    config.add_route('socket_io', 'socket.io/*remaining')
    config.add_view(socketio_service, route_name='socket_io')

    parser = ConfigParser({'here': global_config['here']})
    parser.read(global_config['__file__'])
    for k, v in parser.items('server:main'):
        settings['server:main:' + k] = v

def route_config_auxiliary(config, route_prefix):
    config.add_route('sockjs_home', route_prefix)
    config.add_route('sockjs_message', '%smessage/' % route_prefix)


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
    authn_policy = SessionAuthenticationPolicy(callback=get_groups)
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


def locale_config(config):
    settings = config.registry.settings
    settings['pyramid.locales'] = json.loads(settings['pyramid.locales'])
    from gecoscc.models import Policy, Policies
    for locale in settings['pyramid.locales']:
        if locale == settings['pyramid.default_locale_name']:
            continue
        Policy.__all_schema_nodes__.append(colander.SchemaNode(colander.String(),
                                                               name='name_%s' % locale,
                                                               default='',
                                                               missing=''))
    Policies.policies = Policy(name='policies')
    Policies.__class_schema_nodes__ = [Policies.policies]
    Policies.__all_schema_nodes__ = [Policies.policies]


def main(global_config, **settings):
    """ This function returns a WSGI application.
    """
    settings = dict(settings)
    config = Configurator(root_factory=get_root, settings=settings)

    database_config(config)
    userdb_config(config)
    auth_config(config)
    celery_config(config)
    locale_config(config)

    config.add_translation_dirs('gecoscc:locale/')

    jinja2_config(config)

    config.include('pyramid_jinja2')
    config.include('pyramid_beaker')
    config.include('pyramid_celery')
    config.include('cornice')

    def add_renderer_globals(event):
        current_settings = get_current_registry().settings
        event['help_manual_url'] = current_settings['help_manual_url']

    config.add_subscriber(add_renderer_globals, 'pyramid.events.BeforeRender')

    config.add_subscriber('gecoscc.i18n.setAcceptedLanguagesLocale',
                          'pyramid.events.NewRequest')

    config.add_subscriber('gecoscc.i18n.add_localizer',
                          'pyramid.events.NewRequest')

    route_config(config)
    sockjs_config(config, global_config)

    config.set_request_property(is_logged, 'is_logged', reify=True)
    config.set_request_property(get_jobstorage, 'jobs', reify=True)

    config.scan('gecoscc.views')
    config.scan('gecoscc.api')

    return config.make_wsgi_app()
