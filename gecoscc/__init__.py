#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Antonio Perez-Aranda <ant30tx@gmail.com>
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import json
import os
import pymongo
import sys
import subprocess
import jinja2

from ConfigParser import ConfigParser

from pyramid.authentication import SessionAuthenticationPolicy
from pyramid.authorization import ACLAuthorizationPolicy
from pyramid.config import Configurator
from pyramid.exceptions import ConfigurationError
from pyramid.threadlocal import get_current_registry

from gecoscc.db import MongoDB, get_db
from gecoscc.userdb import get_userdb, get_groups, get_user
from gecoscc.eventsmanager import get_jobstorage
from gecoscc.permissions import is_logged, LoggedFactory, SuperUserFactory, SuperUserOrMyProfileFactory, InternalAccessFactory, RootFactory
from gecoscc.socks import socketio_service

from urlparse import urlsplit
import colander


def read_setting_from_env(settings, key, default=None):
    env_variable = key.upper()
    if env_variable in os.environ:
        return os.environ[env_variable]

    return settings.get(key, default)

def pregen(_request, elements, kw):
    kw.setdefault('rollback', '')
    return elements, kw

def include_file(name):
    with open(name) as f:
        return jinja2.Markup(f.read())

def route_config(config):
    config.add_static_view('static', 'static')
    config.add_route('home', '/', factory=LoggedFactory)
    config.add_route('updates', '/updates/', factory=SuperUserFactory)
    config.add_route('updates_add', '/updates/add/', factory=SuperUserFactory)
    config.add_route('updates_log', '/updates/log/{sequence}/{rollback:.*}', factory=SuperUserFactory, pregenerator=pregen)
    config.add_route('updates_tail', '/updates/tail/{sequence}/{rollback:.*}', factory=SuperUserFactory, pregenerator=pregen)
    
    config.add_route('admins', '/admins/', factory=SuperUserFactory)
    config.add_route('admins_add', '/admins/add/', factory=SuperUserFactory)
    config.add_route('admins_superuser', '/admins/superuser/{username}/', factory=SuperUserFactory)
    config.add_route('admins_ou_manage', '/admins/manage_ou/{username}/', factory=SuperUserFactory)

    config.add_route('admins_edit', '/admins/edit/{username}/', factory=SuperUserOrMyProfileFactory)
    config.add_route('admins_set_variables', '/admins/variables/{username}/', factory=SuperUserOrMyProfileFactory)
    config.add_route('admin_delete', '/admins/delete/', factory=SuperUserOrMyProfileFactory)
    config.add_route('admin_maintenance', '/admins/maintenance/', factory=SuperUserFactory)

    config.add_route('settings', '/settings/', factory=SuperUserFactory)
    config.add_route('settings_save', '/settings/save/', factory=SuperUserFactory)
    config.add_route('reports', '/reports/', factory=SuperUserFactory)
    config.add_route('report_file', '/report', factory=SuperUserFactory)
    config.add_route('computer_logs', '/computer/logs/{node_id}/{filename}', factory=LoggedFactory)
    config.add_route('download_computer_logs', '/download/computer/logs/{node_id}/{filename}', factory=LoggedFactory)
    config.add_route('delete_computer_logs', '/delete/computer/logs/{node_id}/{filename}', factory=LoggedFactory)
    config.add_route('i18n_catalog', '/i18n-catalog/')
    config.add_route('login', '/login/')
    config.add_route('logout', 'logout/')
    config.add_route('forbidden-view', '/error403/')
    config.add_renderer('csv', 'gecoscc.views.reports.CSVRenderer')
    config.add_renderer('pdf', 'gecoscc.views.reports.PDFRenderer')
    config.add_renderer('txt', 'gecoscc.views.computer_logs.TXTRenderer')
    
    config.add_route('statistics', '/admins/statistics/', factory=SuperUserFactory)
    config.add_route('server_status', '/server/status', factory=SuperUserFactory)
    config.add_route('internal_server_status', '/internal/server/status', factory=InternalAccessFactory)
    config.add_route('server_connections', '/server/connections', factory=SuperUserFactory)
    config.add_route('internal_server_connections', '/internal/server/connections', factory=InternalAccessFactory)
    config.add_route('server_log', '/server/log', factory=SuperUserFactory)

    


def sockjs_config(config, global_config):
    settings = config.registry.settings

    settings['sockjs_url'] = settings['sockjs_url']

    config.add_route('socket_io', 'socket.io/*remaining')
    config.add_view(socketio_service, route_name='socket_io')

    parser = ConfigParser({'here': global_config['here']})
    parser.read(global_config['__file__'])
    settings['server:main:worker_class'] = parser.get('server:main', 'worker_class')


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

def check_server_list(config):
    settings = config.registry.settings
    server_name = read_setting_from_env(settings, 'server_name', None)
    if not server_name:
        # Try to get the server name from "hostname" command
        p = subprocess.Popen('hostname', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        server_name, _ = p.communicate()

    if not server_name:
        raise ConfigurationError("server_name option required in gecoscc.ini")

    server_address = read_setting_from_env(settings, 'server_address', None)

    if not server_address:
        raise ConfigurationError("server_address option required in gecoscc.ini")
    
    db = config.registry.settings['mongodb'].get_database()
        
    # Check if this server is in the collection
    server = db.servers.find_one({'name': server_name.strip()})
    if server is None:
        db.servers.insert({'name': server_name.strip(), 'address':server_address.strip()})
    else:
        server['address'] = server_address.strip()
        db.servers.update({'name': server_name.strip()}, server, new=False)
        
    
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

def env_override(value, key):
    return os.getenv(key, value)

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
    settings['BROKER_URL'] = settings['celery_broker_url']


def locale_config(config):
    settings = config.registry.settings
    settings['pyramid.locales'] = json.loads(settings['pyramid.locales'])
    needs_patching = False
    from gecoscc.models import Policy, Policies, Job, Jobs
    for locale in settings['pyramid.locales']:
        if locale == settings['pyramid.default_locale_name']:
            continue
        needs_patching = True
        
        getattr(Policy, '__all_schema_nodes__', []).append(colander.SchemaNode(colander.String(),
                                                                               name='name_%s' % locale,
                                                                               default='',
                                                                               missing=''))
        getattr(Job, '__all_schema_nodes__', []).append(colander.SchemaNode(colander.String(),
                                                                            name='policyname_%s' % locale,
                                                                            default='',
                                                                            missing=''))
    if needs_patching:
        Policies.policies = Policy(name='policies')
        Policies.__class_schema_nodes__ = [Policies.policies]
        Policies.__all_schema_nodes__ = [Policies.policies]

        Jobs.jobs = Job(name='jobs')
        Jobs.__class_schema_nodes__ = [Jobs.jobs]
        Jobs.__all_schema_nodes__ = [Jobs.jobs]


def main(global_config, **settings):
    """ This function returns a WSGI application.
    """
    settings = dict(settings)
    config = Configurator(root_factory=RootFactory, settings=settings)

    # Set Unicode as default encoding
    reload(sys)
    sys.setdefaultencoding('utf-8')
    
    database_config(config)
    userdb_config(config)
    auth_config(config)
    celery_config(config)
    locale_config(config)
    
    check_server_list(config)

    config.add_translation_dirs('gecoscc:locale/')

    jinja2_config(config)

    config.include('pyramid_jinja2')
    config.include('pyramid_beaker')
    config.include('pyramid_celery')
    config.include('cornice')

    jinja2_env = config.get_jinja2_environment()
    jinja2_env.globals["include_file"] = include_file
    jinja2_env.filters['env_override'] = env_override

    def add_renderer_globals(event):
        current_settings = get_current_registry().settings
        event['help_base_url'] = current_settings['help_base_url']
        event['help_policy_url'] = current_settings['help_policy_url']

    config.add_subscriber(add_renderer_globals, 'pyramid.events.BeforeRender')

    config.add_subscriber('gecoscc.i18n.setAcceptedLanguagesLocale',
                          'pyramid.events.NewRequest')

    config.add_subscriber('gecoscc.i18n.add_localizer',
                          'pyramid.events.NewRequest')

    config.add_subscriber('gecoscc.context_processors.set_version',
                          'pyramid.events.NewRequest')

    route_config(config)
    sockjs_config(config, global_config)

    config.set_request_property(is_logged, 'is_logged', reify=True)
    config.set_request_property(get_jobstorage, 'jobs', reify=True)

    config.scan('gecoscc.views')
    config.scan('gecoscc.api')

    return config.make_wsgi_app()
