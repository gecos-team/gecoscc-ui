#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#   Pablo Iglesias <pabloig90@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from six import string_types, text_type
import json
import unittest
import sys
import requests
import io


import mock

from copy import copy, deepcopy

from bson import ObjectId
from celery import current_app
from chef.node import NodeAttributes
from cornice.errors import Errors
from paste.deploy import loadapp
from pyramid import testing
from pyramid.httpexceptions import HTTPForbidden, HTTPFound

from gecoscc.api.chef_status import USERS_OHAI, ChefStatusResource
from gecoscc.api.organisationalunits import OrganisationalUnitResource
from gecoscc.api.computers import ComputerResource, ComputerSupportResource
from gecoscc.api.groups import GroupResource
from gecoscc.api.printers import PrinterResource
from gecoscc.api.repositories import RepositoryResource
from gecoscc.api.storages import StorageResource
from gecoscc.api.users import UserResource
from gecoscc.api.register_computer import RegisterComputerResource
from gecoscc.commands.import_policies import Command as ImportPoliciesCommand
from gecoscc.commands.synchronize_repositories import Command as SyncRepCommand
from gecoscc.commands.update_printers import Command as UpdatePrintersCommand
from gecoscc.commands.mobile_broadband_providers import Command as \
    UpdateISPCommand
from gecoscc.commands.recalc_nodes_policies import Command as \
    RecalcNodePoliciesCommand
from gecoscc.commands.change_password import Command as \
    ChangePasswordCommand
from gecoscc.commands.create_adminuser import Command as CreateAdminUserCommand
from gecoscc.commands.debug_mode_expiration import Command as \
    DebugModeExpirationCommand
    
from gecoscc.db import get_db
from gecoscc.userdb import get_userdb
from gecoscc.permissions import LoggedFactory, SuperUserFactory
from gecoscc.views.portal import home, LoginViews, forbidden_view
from gecoscc.views.admins import admin_add, updates, updates_add, updates_log,\
    updates_download, updates_repeat, updates_tail, admins, admin_edit,\
    admins_ou_manage, admins_set_variables, admin_delete, admin_maintenance,\
    statistics
from pkg_resources import parse_version
from gecoscc.api.admin_users import AdminUserResource
from gecoscc.api.archive_jobs import ArchiveJobsResource
from gecoscc.api.chef_client_run import ChefClientRunResource
from gecoscc.api.help_channel_client import HelpChannelClientLogin,\
    HelpChannelClientFetch, HelpChannelClientCheck, HelpChannelClientAccept,\
    HelpChannelClientFinish
from Crypto.PublicKey import RSA
from gecoscc.api.gca_ous import GCAOuResource
from gecoscc.api.jobs import JobResource
from gecoscc.api.jobs_statistics import JobStatistics
from gecoscc.views.settings import settings, settings_save
from gecoscc.api.mimetypes import MimestypesResource
from gecoscc.api.my_jobs_statistics import MyJobStatistics
from gecoscc.api.nodes import NodesResource
from gecoscc.api.public_computers import ComputerPublicResource
from gecoscc.api.public_ous import OuPublicResource
from gecoscc.api.packages import PackagesResource
from gecoscc.api.policies import PoliciesResource
from gecoscc.api.printer_models import PrinterModelsResource
from gecoscc.api.serviceproviders import ServiceProvidersResource
from gecoscc.api.session import session_get
from gecoscc.api.updates import UpdateResource
from gecoscc.version import __VERSION__ as GCCUI_VERSION

from cgi import FieldStorage
import pyramid
import shutil
import time
import os
from errno import ENOBUFS
from gecoscc.views import computer_logs
from gecoscc.views.reports import reports
from gecoscc.views.report_audit import report_audit_html
from gecoscc.views.report_computer import report_computer_html
from gecoscc.views.report_no_computer_users import report_no_computer_users_html
from gecoscc.views.report_no_user_computers import report_no_user_computers_html
from gecoscc.views.report_permission import report_permission_html
from gecoscc.views.report_printers import report_printers_html
from gecoscc.views.report_status import report_status_html
from gecoscc.views.report_user import report_user_html
from gevent.libev.corecext import NONE
from pip._internal.vcs.bazaar import Bazaar
from gecoscc.utils import update_node
from gecoscc.views.report_storages import report_storages_html
from gecoscc.views.server import internal_server_status,\
    internal_server_connections
import colander
import deform
from deform.widget import FileUploadWidget
from gecoscc.models import unzip_preparer, UpdateNamingValidator,\
    UpdateSequenceValidator, UpdateFileStructureValidator,\
    UpdateControlFileValidator, UpdateScriptRangeValidator, UrlFile,\
    MemoryTmpStore, AdminUserValidator, Unique, LowerAlphaNumeric,\
    deferred_choices_widget, PermissionValidator, UniqueDomainValidator,\
    AUTH_TYPE_CHOICES, GemRepositories

# This url is not used, every time the code should use it, the code is patched
# and the code use de NodeMock class
CHEF_URL = 'https://CHEF_URL/'
CHEF_NODE_ID = '36e13492663860e631f53a00afcdd92d'

# To disable this integration tests, set this value to TRUE
# (To run the integration test you will need a MongoDB server,
# a REDIS server, )
DISABLE_TESTS = False


def create_chef_admin_user_mock(api, settings, username, password=None,
                                email='nobody@nobody.es'):
    pass


def gettext_mock(string, *args, **kwargs):
    return string


def get_cookbook_mock(api, cookbook_name):
    '''
    Returns a static cookbook saved in  json file
    If the cookbook change the cookbook.json should be updated
    '''
    cbmock = None
    with open('gecoscc/test_resources/cookbook.json') as cook_book_file:
        cook_book_json = cook_book_file.read().replace('%(chef_url)s', CHEF_URL)
        cbmock = json.loads(cook_book_json) 
    return cbmock

class MockDeformData(object):
    
    def __init__(self, data):
        self.data = data
        
    def __getitem__(self, item):
        if isinstance(item, int):
            # Get item by number
            n = 0
            for elm in self.data.split('\n'):
                if elm.strip() == '':
                    continue
                
                _, value = elm.split('::')
                if n == item:
                    return value
                n = n + 1
            
        else: 
            # Get item by key
            for elm in self.data.split('\n'):
                if elm.strip() == '':
                    continue
                
                key, value = elm.split('::')
                if key == item:
                    return value
        raise KeyError('No value for: %s'%(item))       
        
    def items(self):
        r = []
        
        for elm in self.data.split('\n'):
            if elm.strip() == '':
                continue
            key, value = elm.split('::')
            r.append((key, value))
        
        return r

class MockResponse(requests.models.Response):
    def __init__(self, status_code, content):
        super(MockResponse, self).__init__()
        self.status_code = status_code
        self.raw = io.BytesIO(content)

def request_get_mock(url, params=None, **kwargs):
    print("REQUEST MOCK: %s"%(url))
    data = False

    # Look for the URL in the cookbook
    with open('gecoscc/test_resources/cookbook.json') as cook_book_file:
        cook_book_json = cook_book_file.read().replace('%(chef_url)s', CHEF_URL)
        cbmock = json.loads(cook_book_json)
        for f in cbmock['files']:
            if f['url'] == url:
                print('Mock file: %s'%(f['name'])) 
                with open('gecoscc/test_resources/%s'%(f['name'])) as mock_file:
                    data = mock_file.read().encode('UTF-8')
                    
    resp = MockResponse(200, data)
    
    return resp

def _check_if_user_belongs_to_admin_group_mock(request, organization, username):
    return True

class ChefApiMock(object):
    def __init__(self):
        self.version = '0.11'
        self.platform = False
        
    @property
    def version_parsed(self):
        return parse_version(self.version)        
     
    def __getitem__(self, item):
        print("CHEF API MOCK: %s"%(item))
        data = None
        if item == '/nodes/%s'%(CHEF_NODE_ID):
            data = {}
            with open('gecoscc/test_resources/node_default.json') as file:
                node_default_json = file.read().replace(
                    '%(chef_url)s', CHEF_URL).replace(
                        '%s(node_name)s', CHEF_NODE_ID)
            data['default'] = json.loads(node_default_json)
            
            with open('gecoscc/test_resources/node_attributes.json') as file:
                node_attributes_json = file.read().replace(
                    '%(chef_url)s', CHEF_URL).replace(
                        '%s(node_name)s', CHEF_NODE_ID)

            data['normal'] = json.loads(node_attributes_json)

        if item == '/cookbooks/gecos_ws_mgmt/_latest/':
            data = get_cookbook_mock(None, None)


        if item == '/clients/%s'%(CHEF_NODE_ID):
            data = {}
            with open('gecoscc/test_resources/client.json') as file:
                client_json = file.read().replace(
                    '%(chef_url)s', CHEF_URL).replace(
                        '%s(node_name)s', CHEF_NODE_ID)
                data = json.loads(client_json)

        if item == '/organizations/default/groups/admins':
            data = {
              "actors": [
                "pivotal",
                "test"
              ],
              "users": [
                "pivotal",
                "test"
              ],
              "clients": [
            
              ],
              "groups": [
                "000000000000ad94b5ddde157c070f0c"
              ],
              "orgname": "inbetweens",
              "name": "admins",
              "groupname": "admins"
            }

        if item == '/organizations/default/association_requests':
            data = [{ 'username': 'newuser' ,'id': 'default' }]
            
        return data
    
    def api_request(self, method, path, headers={}, data=None):
        print("%s: %s"%(method, path))
        resp = {}
        if path.endswith('/association_requests'):
            resp = { 'username': 'newuser'}
        
        if path.endswith('/clients'):
            # Client creation
            resp = { 'private_key': 'TEST private key!',
                     'public_key': 'TEST public key'}
            
        return resp

def get_chef_api_mock(settings, user):
    return ChefApiMock()
    
def _get_chef_api_mock(chef_url, username, chef_pem, chef_ssl_verify,
                       chef_version = '11.0.0'):
    
    return ChefApiMock()

def isinstance_mock(instance, klass):
    '''
    Patch the called isinstance(dest, NodeAttributes) of the delete_dotted
    function. It is in the gecoscc.utils module.
    '''
    if klass is NodeAttributes:
        return isinstance(instance, NodeAttributesMock)
    return isinstance(instance, klass)


NODES = {}


class ClientMock(object):

    '''
    ClientMock emulates Client <chef.node.Client>
    With this class client are emulated
    '''

    def __init__(self, chef_node_id, api):
        super(ClientMock, self).__init__()

    def delete(self):
        pass


class NodeAttributesMock(object):

    '''
    NodeAttributesMock emulates NodeAttributes <chef.node.NodeAttributes>
    '''

    def __init__(self, data, node, node_attr_type='attributes'):
        super(NodeAttributesMock, self).__init__()
        self.data = data
        self.node = node
        self.node_attr_type = node_attr_type

    @property
    def search_path(self):
        return (self.node.default.to_dict(), self.node.attributes.to_dict())

    def to_dict(self):
        return self.data

    def get_dotted(self, key):
        data = self.data
        for k in key.split('.'):
            if k not in data:
                if self.node_attr_type == 'attributes':
                    return self.node.default.get_dotted(key)
                raise KeyError(key)
            data = data[k]
        if isinstance(data, dict):
            data = NodeAttributesMock(data, self.node)
        return data

    def has_dotted(self, key):
        try:
            self.get_dotted(key)
        except KeyError:
            return False
        else:
            return True

    def get(self, key, default=None):
        val = self.data.get(key, None)
        if isinstance(val, dict):
            return NodeAttributesMock(val,
                                      self.node)
        elif val:
            return val
        return default

    def set_dotted(self, key, value):
        data = self.data
        key_splitted = key.split('.')
        for k in key_splitted[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        data[key_splitted[-1]] = value

    def keys(self):
        return self.data.keys()

    def values(self):
        return self.data.values()

    def items(self):
        return self.data.items()

    def pop(self, key):
        return self.data.pop(key)

    def __getitem__(self, key):
        return NodeAttributesMock(self.data.__getitem__(key), self.node,
            self.node_attr_type)

    def __iter__(self):
        return self.data.__iter__()

    def __delitem__(self, key):
        return self.data.__delitem__(key)

    def __nonzero__(self):
        return bool(self.data)


class NodeMock(object):

    '''
    NodeMock emulates NodeAttributes <chef.node.Node>
    With this class and the two previous classes the chef client and chef
    server are emulated
    '''

    def __init__(self, chef_node_id, api):
        super(NodeMock, self).__init__()
        self.name = chef_node_id
        node_default_json = '{}'
        with open('gecoscc/test_resources/node_default.json') as file:
            node_default_json = file.read().replace(
                '%(chef_url)s', CHEF_URL).replace(
                    '%s(node_name)s', chef_node_id)
        self.default = NodeAttributesMock(json.loads(node_default_json), self,
                                          'default')

        if chef_node_id in NODES:
            self.attributes = NodeAttributesMock(copy(NODES[chef_node_id]),
                                                 self)
            self.normal = self.attributes
            self.exists = True
        else:
            node_attributes_json = '{}'
            with open('gecoscc/test_resources/node_attributes.json') as file:
                node_attributes_json = file.read().replace(
                    '%(chef_url)s', CHEF_URL).replace(
                        '%s(node_name)s', chef_node_id)

            node_attributes_json = json.loads(node_attributes_json)
            self.check_no_exists_name(node_attributes_json)
            self.attributes = NodeAttributesMock(node_attributes_json, self)
            self.normal = self.attributes
            self.exists = False

    def check_no_exists_name(self, node_attributes_json):
        name = node_attributes_json['ohai_gecos']['pclabel']
        db = BaseGecosTestCase.get_db()
        exists = db.nodes.find_one({'name': name})
        i = 0
        while exists:
            name = '%s-%s' % (name, i)
            i = i + 1
            exists = db.nodes.find_one({'name': name})
        node_attributes_json['ohai_gecos']['pclabel'] = name
        return node_attributes_json

    def get(self, key, default=None):
        val = self.attributes.get(key, default)
        if val is None:
            val = self.default.get(key, default)
        return val

    def save(self):
        NODES[self.name] = copy(self.attributes.data)
        self.exists = True

    def delete(self):
        del NODES[self.name]

# -------------------------------------------------------------------
# Model classes mocks:
#  These classes must be a copy-paste from model classes but without
#  i18 gettext method for the titles
# -------------------------------------------------------------------
class UpdateModelMock(colander.MappingSchema):
    '''
    Schema for representing an update in form 
    '''
    local_file = colander.SchemaNode(deform.FileData(),
                                     widget=FileUploadWidget(MemoryTmpStore()),
                                     preparer=unzip_preparer,
                                     validator = colander.All(
                                         UpdateNamingValidator(), 
                                         UpdateSequenceValidator(),
                                         UpdateFileStructureValidator(), 
                                         UpdateControlFileValidator(),
                                         UpdateScriptRangeValidator()),
                                     missing=colander.null,
                                     title='Update ZIP')
    remote_file = colander.SchemaNode(UrlFile(),
                                      preparer=unzip_preparer,
                                      validator = colander.All(
                                          UpdateNamingValidator(), 
                                          UpdateSequenceValidator(),
                                          UpdateFileStructureValidator(), 
                                          UpdateControlFileValidator()),
                                      missing=colander.null,
                                      title='URL download')


class BaseUserMock(colander.MappingSchema):
    first_name = colander.SchemaNode(colander.String(),
                                     title='First name',
                                     default='',
                                     missing='')
    last_name = colander.SchemaNode(colander.String(),
                                    title='Last name',
                                    default='',
                                    missing='')


class AdminUserMock(BaseUserMock):
    validator = AdminUserValidator()
    username = colander.SchemaNode(colander.String(),
        title='Username',
        validator=colander.All(
            Unique('adminusers',
             'There is a user with this username: ${val}'),
            LowerAlphaNumeric()))
    password = colander.SchemaNode(colander.String(),
        title='Password',
        widget=deform.widget.PasswordWidget(),
        validator=colander.Length(min=6))
    repeat_password = colander.SchemaNode(colander.String(),
        default='',
        title='Repeat the password',
        widget=deform.widget.PasswordWidget(),
        validator=colander.Length(min=6))
    email = colander.SchemaNode(colander.String(),
        title='Email',
        validator=colander.All(
            colander.Email(),
            Unique('adminusers',
                   'There is a user with this email: ${val}')))

PERMISSIONS = (('READONLY', 'read'),
               ('MANAGE', 'manage'),
               ('LINK', 'link'),
               ('REMOTE', 'remote'))


class AdminUserOUPermMock(colander.MappingSchema):
    ou_selected = colander.SchemaNode(colander.List(),
                                      title='Select an Organization Unit',
                                      widget=deferred_choices_widget)


    permission = colander.SchemaNode(colander.Set(),
                                     title='Permissions',
                                     validator=colander.All(
                                         colander.Length(min=1),
                                         PermissionValidator()),
                                     widget=deform.widget.CheckboxChoiceWidget(
                                         values=PERMISSIONS, inline=True))


class AdminUserOUPermsMock(colander.SequenceSchema):
    permissions = AdminUserOUPermMock(
        title='Collapse/Expand',
        widget=deform.widget.MappingWidget(
        template='mapping_accordion',
        item_template="mapping_item_two_columns"))


class PermissionsMock(colander.MappingSchema):
    perms = AdminUserOUPermsMock(
        title='Permission List',
        widget=deform.widget.SequenceWidget(template='custom_sequence')
    )


class AuthLDAPVariableMock(colander.MappingSchema):
    uri = colander.SchemaNode(colander.String(),
                              title='uri',
                              default='URL_LDAP')
    base = colander.SchemaNode(colander.String(),
                               title='base',
                               default='OU_BASE_USER')
    basegroup = colander.SchemaNode(colander.String(),
                                    title='base group',
                                    default='OU_BASE_GROUP')
    binddn = colander.SchemaNode(colander.String(),
                                 title='binddn',
                                 default='USER_WITH_BIND_PRIVILEGES')
    bindpwd = colander.SchemaNode(colander.String(),
                                  title='bindpwd',
                                  default='PASSWORD_USER_BIND')


class ActiveDirectoryVariableNoSpecificMock(colander.MappingSchema):
    fqdn = colander.SchemaNode(colander.String(),
                               title='FQDN')
    workgroup = colander.SchemaNode(colander.String(),
                                    title='WORKGROUP')


class ActiveDirectoryVariableSpecificMock(colander.MappingSchema):
    sssd_conf = colander.SchemaNode(deform.FileData(),
                                    widget=FileUploadWidget(MemoryTmpStore()),
                                    title='SSSD conf')
    krb5_conf = colander.SchemaNode(deform.FileData(),
                                    widget=FileUploadWidget(MemoryTmpStore()),
                                    title='KRB5 conf')
    smb_conf = colander.SchemaNode(deform.FileData(),
                                   widget=FileUploadWidget(MemoryTmpStore()),
                                   title='SMB conf')
    pam_conf = colander.SchemaNode(deform.FileData(),
                                   widget=FileUploadWidget(MemoryTmpStore()),
                                   title='PAM conf')


class AdminUserVariablesMock(colander.MappingSchema):
    nav_tree_pagesize = colander.SchemaNode(colander.Integer(),
                                  default=10,
                                  missing=10,
                                  title='Navigation tree page size:',
                                  validator=colander.Range(1, 200))
    policies_pagesize = colander.SchemaNode(colander.Integer(),
                                  default=8,
                                  missing=8,
                                  title='Policies list page size:',
                                  validator=colander.Range(1, 200))
    jobs_pagesize = colander.SchemaNode(colander.Integer(),
                                  default=30,
                                  missing=30,
                                  title='Actions list page size:',
                                  validator=colander.Range(1, 200))
    group_nodes_pagesize = colander.SchemaNode(colander.Integer(),
                                  default=10,
                                  missing=10,
                                  title='Group nodes list page size:',
                                  validator=colander.Range(1, 200))
    uri_ntp = colander.SchemaNode(colander.String(),
                                  default='URI_NTP_SERVER.EX',
                                  title='URI ntp')
    auth_type = colander.SchemaNode(colander.String(),
                                    title='Auth type',
                                    default='LDAP',
                                    widget=deform.widget.SelectWidget(
                                        values=AUTH_TYPE_CHOICES))
    specific_conf = colander.SchemaNode(colander.Boolean(),
                                        title='Specific conf',
                                        default=False)
    auth_ldap = AuthLDAPVariableMock(title='Auth LDAP')
    auth_ad = ActiveDirectoryVariableNoSpecificMock(title='Auth Active directory')
    auth_ad_spec = ActiveDirectoryVariableSpecificMock(title='Auth Active directory')
    gem_repos = GemRepositories(title='Gem Repositories',
                                missing=[],
                                default=[],
                                validator=UniqueDomainValidator())

    def get_config_files(self, mode, username):
        return None

    def get_files(self, mode, username, file_name):
        return None

class MaintenanceMock(colander.MappingSchema):
    maintenance_message = colander.SchemaNode(colander.String(),
      validator=colander.Length(max=500),
      widget=deform.widget.TextAreaWidget(rows=10, cols=80, maxlength=500,
        css_class='deform-widget-textarea-maintenance'),
      title='Users will be warned with this message',
      default='',
      missing='')


# -----------------------------------------------------------
# GECOS test base class
# -----------------------------------------------------------

class BaseGecosTestCase(unittest.TestCase):

    def setUp(self):
        '''
        1. Parser test.ini
        2. Add configuration to the application and celery like pyramid do
        3. Drop database
        4. Drop nodes mock
        5. Import policies
        6. Create a basic structure
        '''
        if DISABLE_TESTS: return

        # Since this file imports from gecoscc.api and gecoscc.api
        # import from gecoscc.tasks, the tasks are binding to a "default"
        # Celery app before the Pyramid celery app is created and configured
        #
        # So, we need to bind all the tasks to the Pyramid celery task  
        from celery._state import get_current_app
        default_celery_app = get_current_app()
        print("Current app (before celery setup): %s"%(default_celery_app))
        gecos_tasks = default_celery_app.tasks
        
        app_sec = 'config:config-templates/test.ini'
        name = None
        relative_to = '.'
        kw = {'global_conf': {}}
        config = loadapp(app_sec, name=name, relative_to=relative_to, **kw)

        # Bind all the tasks to the Pyramid celery task
        from pyramid_celery import celery_app
        for task in gecos_tasks.keys():
            celery_app.register_task(gecos_tasks[task])  

        
        self.config = config
        self.registry = config.application.wsgi_app.registry
        testing.setUp(self.registry)
        current_app.add_defaults(self.registry.settings)
        self.drop_database()
        self.drop_mock_nodes()
        self.import_policies()
        self.create_basic_structure()

    def tearDown(self):
        testing.tearDown()
        

    @classmethod
    def get_db(self):
        '''
        Useful method, returns a database connection
        '''
        request = testing.DummyRequest()
        return get_db(request)

    def drop_database(self):
        '''
        Useful method, drop test database
        '''
        c = self.registry.settings['mongodb'].get_connection()
        db_name = self.registry.settings['mongodb'].database_name
        c.drop_database(db_name)

    def drop_mock_nodes(self):
        '''
        Useful method, drop mock nodes
        '''
        global NODES
        NODES = {}

    def get_dummy_request(self, is_superuser=True):
        '''
        Useful method, returns a typical request, with the same request
        properties than pyramid add (see gecoscc/__init__)
        '''
        request = testing.DummyRequest()
        request.db = get_db(request)
        request.userdb = get_userdb(request)
        if is_superuser is True:
            user = request.db.adminusers.find_one({'is_superuser': True})
            if not user:
                user = request.userdb.create_user('test', 'test',
                    'test@example.com', {'is_superuser': True})
            request.user = request.db.adminusers.find_one(
                {'is_superuser': True})
        else:
            user = request.db.adminusers.find_one({'is_superuser': False})
            if not user:
                user = request.userdb.create_user('test_no_super',
                    'test_no_super', 'test_no_super@example.com',
                    {'is_superuser': False})
            request.user = request.db.adminusers.find_one(
                {'is_superuser': False})

        return request

    def dummy_get_request(self, data, schema=None):
        '''
        Useful method, returns a typical get request
        '''
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        if schema:
            request.matchdict['oid'] = data['_id']
        request.path = '/api/%ss/%s/' % (data['type'], data['_id'])
        return request

    def get_dummy_json_post_request(self, data, schema=None):
        '''
        Useful method, returns a typical post request
        '''
        request = self.get_dummy_request()
        request.method = 'POST'
        request.json = json.dumps(data)
        request.errors = Errors()
        if schema:
            request.validated = schema().serialize(data)
            del request.validated['_id']
        return request

    def get_dummy_json_put_request(self, data, schema=None, is_superuser=True,
        path=None):
        '''
        Useful method, returns a typical put request
        '''
        request = self.get_dummy_request(is_superuser)
        request.method = 'PUT'
        request.errors = Errors()
        if schema:
            if isinstance(data['_id'], string_types):
                data['_id'] = ObjectId(data['_id'])
            serialize_data = schema().serialize(data)
            request.validated = deepcopy(serialize_data)
            request.matchdict['oid'] = request.validated['_id']
            request.validated['_id'] = ObjectId(request.validated['_id'])

            node_type = data.get('type', '')
            data_validated_hook = getattr(self,
                'data_validated_hook_%s' % node_type, None)
            if data_validated_hook:
                data_validated_hook(request.validated)
                
            request.json = json.dumps(serialize_data)
            request.path = '/api/%ss/%s/' % (serialize_data['type'],
                serialize_data['_id'])
                
        else:
            request.json = data
            request.path = path

        return request

    def get_dummy_delete_request(self, data, schema=None):
        '''
        Useful method, returns a typical delete request
        '''
        request = self.get_dummy_request()
        if schema:
            request.matchdict['oid'] = data['_id']
        request.method = 'DELETE'
        request.path = '/api/%ss/%s/' % (data['type'], data['_id'])
        return request

    def data_validated_hook_user(self, data):
        for i, comp in enumerate(data.get('computers', [])):
            comp_id = data['computers'][i]
            if isinstance(comp_id, string_types):
                data['computers'][i] = ObjectId(comp_id)
        for i, comp in enumerate(data.get('memberof', [])):
            comp_id = data['memberof'][i]
            if isinstance(comp_id, string_types):
                data['memberof'][i] = ObjectId(comp_id)

    def data_validated_hook_computer(self, data):
        for i, member in enumerate(data.get('memberof', [])):
            member_id = data['memberof'][i]
            if isinstance(member_id, string_types):
                data['memberof'][i] = ObjectId(member_id)

    def data_validated_hook_group(self, data):
        for i, comp in enumerate(data.get('members', [])):
            comp_id = data['members'][i]
            if isinstance(comp_id, string_types):
                data['members'][i] = ObjectId(comp_id)

    def cleanErrorJobs(self):
        '''
        Clean all jobs.
        '''
        db = self.get_db()
        db.jobs.delete_many({})

    def assertNoErrorJobs(self):
        '''
        Useful method, check there are not any job with error (or even success)
        every job should be "processing"
        '''
        db = self.get_db()
        self.assertEqual(db.jobs.count_documents({'status': 'errors'}), 0)

    def assertEmitterObjects(self, node_policy, db_emiters, fields):
        '''
        Useful method, check if the second list has the same values than the
        first
        '''
        node_policy.sort(key=lambda e: e['uri'])
        db_emiters.sort(key=lambda e: e['uri'])

        for i, emiter in enumerate(db_emiters):
            self.assertEqualObjects(node_policy[i], emiter, fields=fields)

    def assertItemsEqual(self, list1, list2):
        '''
        Useful method, check that both list contains the same items
        '''
        self.assertEqual(len(list1), len(list2),
            'The lists have different lengths')
        
        for elm in list1:
            self.assertTrue(elm in list2, 
                '{0} not in {1}'.format(elm, list2))
        

    def assertEqualObjects(self, data, new_data, schema_data=None,
        schema_new_data=None, fields=None):
        '''
        Useful method, check the second dictionary has the same values than
        the first. The second dictionary could have other attrs
        '''
        if schema_data:
            data = schema_data().serialize(data)
        if schema_new_data:
            new_data = schema_new_data().serialize(new_data)
        for field_name, field_value in data.items():
            if fields is not None and field_name not in fields:
                continue
            self.assertEqual(field_value, new_data[field_name])

    def assertDeleted(self, field_name, field_value):
        '''
        Useful method, check if a element has been deleted
        '''
        node_deleted = self.get_db().nodes.find_one({field_name: field_value})
        self.assertIsNone(node_deleted)

    def assertIsPaginatedCollection(self, api_class):
        '''
        Useful method. check if data is a paginated collection
        '''
        request = self.get_dummy_request()
        node_api = api_class(request)
        data = node_api.collection_get()
        self.assertIsInstance(data['nodes'], list)
        self.assertIsInstance(data['pages'], int)
        self.assertIsInstance(data['pagesize'], int)

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def create_basic_structure(self, get_cookbook_method,
        get_cookbook_method_tasks):
        '''
        1. Create a flag (organisational unit level 0)
        2. Create a domain (organisational unit level 1)
        3. Create a organisational unit
        '''
        print("Creating basic structure...")
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        data = {'name': 'Flag',
                'type': 'ou',
                'path': 'root',
                'source': 'gecos'}

        request_post = self.get_dummy_json_post_request(data,
            OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request_post)
        flag_new = ou_api.collection_post()

        data, domain = self.create_domain('Domain 1', flag_new)
        data, ou = self.create_ou('OU 1')
        # 2 - Create user in domain
        username = 'usertest'
        data, new_user = self.create_user(username, ou['name'])        
        print("Basic structure created!")

    @mock.patch('gecoscc.commands.import_policies.get_cookbook')
    def import_policies(self, get_cookbook_method):
        '''
        Useful method, import the policies
        '''

        print("Importing policies...")
        get_cookbook_method.side_effect = get_cookbook_mock
        argv_bc = sys.argv
        sys.argv = ['pmanage', 'config-templates/test.ini', 'import_policies',
                    '-a', 'test', '-k', 'gecoscc/test_resources/media/users/'
                    'test/chef_client.pem', '-d']
        command = ImportPoliciesCommand('config-templates/test.ini')
        command.command()
        sys.argv = argv_bc
        print("Policies imported")

    def sync_repositories(self):
        '''
        Useful method, synchronize repositories
        '''
        argv_bc = sys.argv
        sys.argv = ['pmanage', 'config-templates/test.ini',
                    'synchronize_repositories', '-c']
        command = SyncRepCommand('config-templates/test.ini')
        command.command()
        sys.argv = argv_bc

    def update_printers(self):
        '''
        Useful method, update printers data
        '''
        argv_bc = sys.argv
        sys.argv = ['pmanage', 'config-templates/test.ini',
                    'update_printers']
        command = UpdatePrintersCommand('config-templates/test.ini')
        command.command()
        sys.argv = argv_bc

    @mock.patch('gecoscc.commands.mobile_broadband_providers.get_cookbook')
    @mock.patch('gecoscc.commands.mobile_broadband_providers._get_chef_api')
    @mock.patch('gecoscc.commands.mobile_broadband_providers.requests.get')
    def update_ISP(self, request_get_method, get_chef_api_method,
                   get_cookbook_method):
        '''
        Useful method, update ISP data
        '''
        request_get_method.side_effect = request_get_mock
        get_cookbook_method.side_effect = get_cookbook_mock
        get_chef_api_method.side_effect = _get_chef_api_mock
        
        argv_bc = sys.argv
        sys.argv = ['pmanage', 'config-templates/test.ini',
                    'mobile_broadband_providers', '-a', 'test', '-k',
                    'gecoscc/test_resources/media/users/test/chef_client.pem']
        command = UpdateISPCommand('config-templates/test.ini')
        command.command()
        sys.argv = argv_bc

    def change_password_command(self):
        '''
        Useful method, change password.
        '''
        argv_bc = sys.argv
        sys.argv = ['pmanage', 'config-templates/test.ini',
                    'change_password', '--username', 'test', '-n']
        command = ChangePasswordCommand('config-templates/test.ini')
        command.command()
        sys.argv = argv_bc

    def create_admin_user(self, username, mail):
        '''
        Useful method, create an administrator user.
        '''
        argv_bc = sys.argv
        sys.argv = ['pmanage', 'config-templates/test.ini',
                    'create_adminuser', '--username', username, '--email',
                    mail, '-n']
        command = CreateAdminUserCommand('config-templates/test.ini')
        command.command()
        sys.argv = argv_bc
        
    def debug_mode_expiration_command(self, username):
        '''
        Useful method, debug mode expiration command.
        '''
        argv_bc = sys.argv
        sys.argv = ['pmanage', 'config-templates/test.ini',
                    'debug_mode_expiration', '--administrator', username]
        command = DebugModeExpirationCommand('config-templates/test.ini')
        command.command()
        sys.argv = argv_bc


    def recalc_policies(self):
        '''
        Useful method, recalculate policies
        '''
        argv_bc = sys.argv
        sys.argv = ['pmanage', 'config-templates/test.ini',
                    'recalc_nodes_policies', '-a', 'test']
        command = RecalcNodePoliciesCommand('config-templates/test.ini')
        command.command()
        sys.argv = argv_bc

    def create_group(self, group_name, ou_name='OU 1'):
        '''
        Useful method, create a group
        '''

        data = {'name': group_name,
                'type': 'group',
                'source': 'gecos'}

        return self.create_node(data, GroupResource, ou_name)

    def create_printer(self, printer_name, ou_name='OU 1'):
        '''
        Useful method, create a printer
        '''
        data = {'connection': 'network',
                'manufacturer': 'Calcomp',
                'model': 'Artisan 1023 penplotter',
                'name': printer_name,
                'oppolicy': 'default',
                'printtype': 'laser',
                'source': 'gecos',
                'type': 'printer',
                'uri': 'http://%s.example.com' % printer_name}
        return self.create_node(data, PrinterResource, ou_name)

    def create_repository(self, repository_name, ou_name='OU 1'):
        '''
        Useful method, create a repository
        '''
        data = {'name': repository_name,
                'repo_key': repository_name + 'CJAER23',
                'key_server': '%s.repository.com' % repository_name,
                'type': 'repository',
                'source': 'gecos',
                'uri': 'http://%s.repository.com' % repository_name,
                }
        return self.create_node(data, RepositoryResource, ou_name)

    def create_storage(self, storage_name, ou_name='OU 1'):
        '''
        Useful method, create a Storage
        '''
        data = {'name': storage_name,
                'type': 'storage',
                'source': 'gecos',
                'uri': 'http://%s.storage.com' % storage_name}
        return self.create_node(data, StorageResource, ou_name)

    def create_user(self, username, ou_name='OU 1'):
        '''
        Useful method, create an User
        '''
        data = {'name': username,
                'email': '%s@example.com' % username,
                'type': 'user',
                'source': 'gecos'}
        return self.create_node(data, UserResource, ou_name)

    def create_ou(self, ou_name, domain_name='Domain 1'):
        '''
        Useful method, create an OU
        '''
        db = self.get_db()
        domain = db.nodes.find_one({'name': domain_name})

        data = {'name': ou_name,
                'type': 'ou',
                'path': '%s,%s' % (domain['path'], domain['_id']),
                'source': 'gecos'}
        return self.create_node(data, OrganisationalUnitResource,
                ou_name=domain_name)

    def create_domain(self, ou_name, flag):
        '''
        Useful method, create a Domain
        '''
        data = {'name': ou_name,
                'type': 'ou',
                'path': '%s,%s' % (flag['path'], flag['_id']),
                'master': 'gecos',
                'source': 'gecos'}
        return self.create_node(data, OrganisationalUnitResource,
                ou_name=flag['name'])

    def create_node(self, data, api_class, ou_name='OU 1'):
        '''
        Useful method, create a node
        '''
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': ou_name})

        data['path'] = '%s,%s' % (ou_1['path'], ou_1['_id'])

        request_post = self.get_dummy_json_post_request(data,
            api_class.schema_detail)
        object_api = api_class(request_post)

        return (data, object_api.collection_post())

    def update_node(self, obj, field_name, field_value, api_class,
        is_superuser=True):
        '''
        Useful method, update a node
        '''
        if isinstance(obj[field_name], list):
            obj[field_name].append(field_value)
        else:
            obj[field_name] = field_value
        request_put = self.get_dummy_json_put_request(obj,
            api_class.schema_detail, is_superuser)
        api = api_class(request_put)
        return api.put()

    def delete_node(self, node, api_class):
        '''
        Useful method, delete a node
        '''
        request = self.dummy_get_request(node, api_class.schema_detail)
        node_api = api_class(request)
        node = node_api.get()

        request_delete = self.get_dummy_delete_request(node,
            api_class.schema_detail)
        api = api_class(request_delete)
        return api.delete()

    def register_computer(self, ou_name='OU 1', chef_node_id=None):
        '''
        Useful method, register a computer
        '''
        ou = self.get_db().nodes.find_one({'name': ou_name})
        chef_node_id = chef_node_id or CHEF_NODE_ID
        data = {'ou_id': ou['_id'],
                'node_id': chef_node_id}
        request = self.get_dummy_request()
        request.POST = data
        computer_response = RegisterComputerResource(request)
        response = computer_response.post()
        self.assertEqual(response['ok'], True)

    @mock.patch('gecoscc.views.admins._check_if_user_belongs_to_admin_group')
    def add_admin_user(self, username, mock_function):
        '''
        Userful method, register an admin User
        '''
        mock_function.side_effect = _check_if_user_belongs_to_admin_group_mock
        data = {'username': username,
                'first_name': '',
                'last_name': '',
                'password': '123123',
                'repeat_password': '123123',
                'email': '%s@example.com' % username,
                '_submit': '_submit',
                '_charset_': 'UTF-8',
                '__formid__': 'deform'}
        request = self.get_dummy_request()
        request.POST = data
        context = SuperUserFactory(request)
        admin_add(context, request)

    def assign_user_to_node(self, gcc_superusername, chef_node_id, username):
        '''
        Useful method, assign an user to a node
        '''
        node = NodeMock(chef_node_id, None)
        users = copy(node.attributes.get_dotted(USERS_OHAI))
        users.append({'gid': 1000,
                      'home': '/home/%s' % username,
                      'sudo': False,
                      'uid': 1000,
                      'username': username})
        node.attributes.set_dotted(USERS_OHAI, users)
        node.save()
        
        user = self.get_db().nodes.find_one({'name': username})
        computer = self.get_db().nodes.find_one({'node_chef_id': chef_node_id})
        computers = user.get('computers', [])
        if computer['_id'] not in computers:
            computers.append(computer['_id'])
            self.get_db().nodes.update_one({'_id': user['_id']},
                                           {'$set': {'computers': computers}})
       

    def assign_group_to_node(self, node_name, api_class, group):
        '''
        Useful method, assign group to node (user or workstation)
        '''
        node = self.get_db().nodes.find_one({'name': node_name})
        request = self.dummy_get_request(node, api_class.schema_detail)
        node_api = api_class(request)
        node = node_api.get()

        id_group = group['_id']
        id_group = ObjectId(id_group)
        if node['type'] == 'user':
            id_computer = node['computers']
            node['computers'] = [ObjectId(id_computer[0])]
        if node['memberof'] != []:
            id_grupo = node['memberof']
            node['memberof'] = [ObjectId(id_grupo[0])]

        self.update_node(obj=node,
                         field_name='memberof',
                         field_value=id_group,
                         api_class=api_class)

    def add_and_get_policy(self, node, chef_node_id, api_class, policy_path):
        '''
        Useful method, add policy to node and return this policy
        '''
        request_put = self.get_dummy_json_put_request(node,
            api_class.schema_detail)
        node_api = api_class(request_put)
        #print("add_and_get_policy json={0}".format(request_put.json))
        node_update = node_api.put()
        if node_update is not None:
            self.assertEqualObjects(node, node_update, api_class.schema_detail)

        node = NodeMock(chef_node_id, None)
        try:
            node_policy = node.attributes.get_dotted(policy_path)
        except KeyError:
            print("ERROR: No '%s' key!"%(policy_path))
            node_policy = []
        return node_policy

    def remove_policy_and_get_dotted(self, node, chef_node_id, api_class,
        policy_path):
        '''
        Useful method, remove policy from node and return dotted
        '''
        node['policies'] = {}
        request_put = self.get_dummy_json_put_request(node, api_class.schema_detail)
        node_api = api_class(request_put)
        node_updated = node_api.put()
        self.assertEqualObjects(node, node_updated, api_class.schema_detail)
        node = NodeMock(chef_node_id, None)
        return node.attributes.get_dotted(policy_path)

    def get_default_policies(self):
        policies = {"package_res_policy": {
                'policy': self.get_default_ws_policy(),
                'path': self.get_default_ws_policy()['path'] + '.package_list',
                'policy_data_node_1': {'package_list': [
                    {'name': 'gimp', 'version': 'latest', 'action': 'add'}]},
                'policy_data_node_2': {'package_list': [
                    {'name': 'libreoffice', 'version': 'latest', 'action':
                     'add'}]}},
            "remote_shutdown_res": {'policy':
                self.get_default_ws_policy(slug='remote_shutdown_res'),
                'path': self.get_default_ws_policy(slug=
                    'remote_shutdown_res')['path'] + '.shutdown_mode',
                'policy_data_node_1': {'shutdown_mode': 'reboot'},
                'policy_data_node_2': {'shutdown_mode': 'halt'}}}
        return policies

    def get_default_policies_user(self):
        policies = {"user_apps_autostart_res": {
                'policy': self.get_default_user_policy(
                    slug='user_apps_autostart_res'),
                'path': self.get_default_user_policy(
                    slug="user_apps_autostart_res")['path'] + '.users.',
                'policy_data_node_1': {"desktops": [
                    {"name": "kate", "action": "add"}]},
                'policy_data_node_2': {"desktops": [
                    {"name": "sublime", "action": "add"}]}},
            "desktop_background_res": {
                'policy': self.get_default_user_policy(
                    slug='desktop_background_res'),
                'path': self.get_default_user_policy(
                    slug="desktop_background_res")['path'] + '.users.',
                'policy_data_node_1': {"desktop_file": "mountain.png"},
                'policy_data_node_2': {"desktop_file": "river.png"}}}
        return policies

    def apply_mocks(self, get_chef_api_method=None, get_cookbook_method=None,
        get_cookbook_method_tasks=None, NodeClass=None, ChefNodeClass=None,
        isinstance_method=None, gettext=None,
        create_chef_admin_user_method=None, ChefNodeStatusClass=None,
        TaskNodeClass=None, TaskClientClass=None, ClientClass=None):
        '''
        mocks
        '''
        if get_chef_api_method is not None:
            get_chef_api_method.side_effect = _get_chef_api_mock
        if get_cookbook_method is not None:
            get_cookbook_method.side_effect = get_cookbook_mock
        if get_cookbook_method_tasks is not None:
            get_cookbook_method_tasks.side_effect = get_cookbook_mock
        if NodeClass is not None:
            NodeClass.side_effect = NodeMock
        if ChefNodeClass is not None:
            ChefNodeClass.side_effect = NodeMock
        if isinstance_method is not None:
            isinstance_method.side_effect = isinstance_mock
        if gettext is not None:
            gettext.side_effect = gettext_mock
        if create_chef_admin_user_method is not None:
            create_chef_admin_user_method.side_effect = \
                create_chef_admin_user_mock
        if ChefNodeStatusClass is not None:
            ChefNodeStatusClass.side_effect = NodeMock
        if TaskNodeClass is not None:
            TaskNodeClass.side_effect = NodeMock
        if TaskClientClass is not None:
            TaskClientClass.side_effect = ClientMock
        if ClientClass is not None:
            ClientClass.side_effect = ClientMock

    def get_default_user_policy(self, slug='user_launchers_res'):
        '''
        Useful method, get the default user policy
        '''
        return self.get_db().policies.find_one({'slug': slug})

    def get_default_ws_policy(self, slug='package_res'):
        '''
        Useful method, get the default ou policy
        '''
        return self.get_db().policies.find_one({'slug': slug})


class BasicTests(BaseGecosTestCase):

    def test_01_home(self):
        '''
        Test 1: Check the home works
        '''
        if DISABLE_TESTS: return
        
        # 1 - Create request access to home view's
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = home(context, request)
        # 2 - Check if the response is valid
        self.assertEqual(json.loads(response['websockets_enabled']), False)
        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_02_printers(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 2: Create, update and delete a printer
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_cookbook_method=get_cookbook_method,
            get_cookbook_method_tasks=get_cookbook_method_tasks)
        self.cleanErrorJobs()
        self.assertIsPaginatedCollection(api_class=PrinterResource)

        # 1 - Create printer
        data, new_printer = self.create_printer('Testprinter')

        # 2 - Verification that the printers has been created successfully
        self.assertEqualObjects(data, new_printer)

        # 3 - Update printer's description
        printer_updated = self.update_node(obj=new_printer,
            field_name='description', field_value=u'Test',
            api_class=PrinterResource)

        # 4 - Verification that printer's description has been updated
        # successfully
        self.assertEqualObjects(new_printer, printer_updated,
            PrinterResource.schema_detail)

        # 5 - Delete printer
        self.delete_node(printer_updated, PrinterResource)

        # 6 - Verification that the printers has been deleted successfully
        self.assertDeleted(field_name='name', field_value='Printer tests')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_03_shared_folder(self, get_cookbook_method,
            get_cookbook_method_tasks):
        '''
        Test 3: Create, update and delete a shared folder
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_cookbook_method=get_cookbook_method,
            get_cookbook_method_tasks=get_cookbook_method_tasks)
        self.cleanErrorJobs()
        self.assertIsPaginatedCollection(api_class=StorageResource)

        # 1 - Create shared folder
        data, new_folder = self.create_storage('test_storage')

        # 2 - Verification that the shared folder has been created successfully
        self.assertEqualObjects(data, new_folder)

        # 3 - Update shared folder's URI
        folder_updated = self.update_node(obj=new_folder, field_name='uri',
            field_value=u'Test', api_class=StorageResource)
        # 4 - Verification that shared folder's URI has been updated
        # successfully
        self.assertEqualObjects(new_folder, folder_updated,
            StorageResource.schema_detail)

        # 5 - Delete shared folder
        self.delete_node(folder_updated, StorageResource)

        # 6 - Verification that the shared folder has been deleted successfully
        self.assertDeleted(field_name='name', field_value='Folder tests')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_04_repository(self, get_cookbook_method,
        get_cookbook_method_tasks):
        '''
        Test 4: Create, update and delete a repository
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_cookbook_method=get_cookbook_method,
            get_cookbook_method_tasks=get_cookbook_method_tasks)
        self.cleanErrorJobs()
        self.assertIsPaginatedCollection(api_class=RepositoryResource)
        # 1 - Create repository
        data, new_repository = self.create_repository('Repo')

        # 2 - Verification that the repository has been created successfully
        self.assertEqualObjects(data, new_repository)

        # 3 - Update repository's URI
        repository_update = self.update_node(obj=new_repository,
            field_name='uri', field_value=u'Test', api_class=RepositoryResource)

        # 4 - Verification that shared folder's URI has been updated
        # successfully
        self.assertEqualObjects(new_repository, repository_update,
            RepositoryResource.schema_detail)

        # 5 - Delete repository
        self.delete_node(repository_update, RepositoryResource)

        # 6 - Verification that the repository has been deleted successfully
        self.assertDeleted(field_name='name', field_value='Repo')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_05_user(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 5: Create, update and delete an user
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_cookbook_method=get_cookbook_method,
            get_cookbook_method_tasks=get_cookbook_method_tasks)
        self.cleanErrorJobs()
        self.assertIsPaginatedCollection(api_class=UserResource)
        # 1 - Create user
        data, new_user = self.create_user('testuser')

        # 2 - Verification that the user has been created successfully
        self.assertEqualObjects(data, new_user)

        # 3 - Update user's first name
        user_updated = self.update_node(obj=new_user, field_name='first_name',
            field_value=u'Another name', api_class=UserResource)

        # 4 - Verification that user's first name has been updated successfully
        self.assertEqualObjects(new_user, user_updated,
            UserResource.schema_detail)

        # 5 - Delete user
        self.delete_node(user_updated, UserResource)

        # 6 - Verification that the user has been deleted successfully
        self.assertDeleted(field_name='first_name', field_value='Another name')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_06_group(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 6: Creation and delete a group
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_cookbook_method=get_cookbook_method,
            get_cookbook_method_tasks=get_cookbook_method_tasks)
        self.cleanErrorJobs()
        self.assertIsPaginatedCollection(api_class=GroupResource)
        # 1 - Create group
        data, new_group = self.create_group('testgroup')

        # 2 - Verification that the group has been created successfully
        self.assertEqualObjects(data, new_group)

        # 3 - Delete group
        self.delete_node(new_group, GroupResource)

        # 4 - Verification that the group has been deleted successfully
        self.assertDeleted(field_name='name', field_value='group')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_07_computer(self, get_chef_api_method, get_cookbook_method,
        get_cookbook_method_tasks, NodeClass, ChefNodeClass, TaskNodeClass,
        ClientClass, isinstance_method):
        '''
        Test 7: Create, update and delete a computer
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, TaskNodeClass=TaskNodeClass,
            ClientClass=ClientClass)
        self.cleanErrorJobs()
        
        # 1 - Register workstation
        self.register_computer()

        # 2  Verification that the workstation has been registered successfully
        computer = self.get_db().nodes.find_one({'name': 'testing'})

        # 3 Update workstation's type
        request = self.get_dummy_request()
        computer_api = ComputerResource(request)
        computer = computer_api.collection_get()
        computer_updated = self.update_node(obj=computer['nodes'][0],
            field_name='family', field_value=u'laptop',
            api_class=ComputerResource)

        # 4 - Verification that the workstation's type has been udpated
        # successfully
        self.assertEqualObjects(computer['nodes'][0], computer_updated,
            ComputerResource.schema_detail)

        # 5 - Delete workstation
        self.delete_node(computer_updated, ComputerResource)

        # 6 - Verification that the workstation has been deleted successfully
        self.assertDeleted(field_name='name', field_value='testing')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_08_OU(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 8: Create, update and delete a OU
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_cookbook_method=get_cookbook_method,
            get_cookbook_method_tasks=get_cookbook_method_tasks)
        self.cleanErrorJobs()
        self.assertIsPaginatedCollection(api_class=OrganisationalUnitResource)
        # 1 - Create OU
        data, new_ou = self.create_ou('OU 2')

        # 2 - Verification that the OU has been created successfully
        self.assertEqualObjects(data, new_ou)

        # 3 - Update OU's extra
        ou_updated = self.update_node(obj=new_ou,
                                      field_name='extra',
                                      field_value=u'Test',
                                      api_class=OrganisationalUnitResource)

        # 4 - Verification that OU has been updated successfully
        self.assertEqualObjects(new_ou, ou_updated,
            OrganisationalUnitResource.schema_detail)

        # 5 - Delete OU
        self.delete_node(ou_updated, OrganisationalUnitResource)

        # 6 - Verification that the OU has been deleted successfully
        self.assertDeleted(field_name='extra', field_value='Test')

        self.assertNoErrorJobs()


    def test_09_auth_config(self):
        '''
        Test 9: Check the configuration of a user
        '''
        if DISABLE_TESTS: return
        
        # 1 - Create request access to auth config view's
        request = self.get_dummy_request()
        node_api = AdminUserResource(request)
        response = node_api.get()
        
        # 2 - Check if the response is valid
        self.assertEqual(response['version'],
            self.registry.settings['firstboot_api.version'])
        self.assertNoErrorJobs()

    def test_10_archive_jobs(self):
        '''
        Test 10: Execute test_08 to create jobs and after that archive the jobs
        '''
        if DISABLE_TESTS: return

        self.test_08_OU()
        
        # Ensure that thera are jobs that haven't been archived
        db = self.get_db()
        self.assertNotEqual(db.jobs.count_documents({'archived': False}), 0)

        # Archive all the jobs of this user
        request = self.get_dummy_request()
        node_api = ArchiveJobsResource(request)
        response = node_api.put()
        self.assertEqual(response['ok'], 'test')
        
        # Ensure that all the jobs have been archived
        self.assertEqual(db.jobs.count_documents({'archived': False}), 0)


    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_11_chef_client_run(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 11: Check the Chef node lockup
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()
        
        # 1 - Register workstation in OU
        chef_node_id = CHEF_NODE_ID
        self.register_computer()
        
        # 2-  Register admin
        admin_username = 'superuser'
        self.add_admin_user(admin_username)
        
        # 3 - Create and register user in chef node
        username = 'usertest'
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        
        
        # 4 - Create request access to the node lockup
        # (Test invalid request)
        request_put = self.get_dummy_json_put_request({},
            path='/chef-client/run/')
        node_api = ChefClientRunResource(request_put)
        response = node_api.put()
        self.assertEqual(response['ok'], False)
        
        # (Test invalid request)
        data ={'node_id': CHEF_NODE_ID}
        request_put = self.get_dummy_json_put_request(data,
            path='/chef-client/run/')
        request_put.POST = data
        node_api = ChefClientRunResource(request_put)
        response = node_api.put()
        self.assertEqual(response['ok'], False)
        
        # (Test valid request)
        data ={'node_id': CHEF_NODE_ID, 'gcc_username':  admin_username}
        request_put = self.get_dummy_json_put_request(data,
            path='/chef-client/run/')
        request_put.POST = data
        node_api = ChefClientRunResource(request_put)
        response = node_api.put()
        
        # 5 - Check if the response is valid
        self.assertEqual(response['ok'], True)
        
        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_12_upload_logs(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 12: Upload log files
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()
        
        # 1 - Register workstation in OU
        chef_node_id = CHEF_NODE_ID
        self.register_computer()
        
        # 2-  Register admin
        admin_username = 'superuser'
        self.add_admin_user(admin_username)
        
        # 3 - Create and register user in chef node
        username = 'usertest'
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        
        
        # 4 - Create request upload the log files
        logs = {
            'date': '2021-01-28 12:00:00',
            'files': { 
                'test.log': {
                    'content': 'Hello world!',
                    'size': 12        
                }
            }
        }
        
        data ={
            'node_id': CHEF_NODE_ID,
            'gcc_username':  admin_username,
            'logs': json.dumps(logs)
        }
        request_post = self.get_dummy_json_post_request(data)
        request_post.POST = data
        node_api = ChefClientRunResource(request_post)
        response = node_api.post()
        
        # 5 - Check if the response is valid
        self.assertEqual(response['ok'], True)
        
        # 6 - Get the computer and check the logs
        db = self.get_db()
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer,
            ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()

        self.assertEqual('test.log', computer['logs']['files'][0]['filename'])
        
        self.assertNoErrorJobs()
        
        # 7 - Get the log file
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        request.matchdict = {
            'node_id': str(computer['_id']),
            'filename': 'test.log'
        }
        response = computer_logs.get_log_file(context, request)
        self.assertEqual(response['data']['content'], 'Hello world!')
        
        
        # 8 - Download the log file
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        request.matchdict = {
            'node_id': str(computer['_id']),
            'filename': 'test.log'
        }
        response = computer_logs.download_log_file(context, request)
        self.assertEqual(response['data']['content'], 'Hello world!')
        
        # 9 - Delete the log file
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        request.matchdict = {
            'node_id': str(computer['_id']),
            'filename': 'test.log'
        }
        response = computer_logs.delete_log_file(context, request)
        self.assertEqual(response['ok'], True)
        


    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_13_update_chef_status(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 13: Upload status after running chef-client in the workstation
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()
        
        # 1 - Register workstation in OU
        chef_node_id = CHEF_NODE_ID
        self.register_computer()
        
        # 2-  Register admin
        admin_username = 'superuser'
        self.add_admin_user(admin_username)
        
        # 3 - Create and register user in chef node
        username = 'usertest'
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        
        
        # 4 - Create request
        data ={'node_id': CHEF_NODE_ID, 'gcc_username':  admin_username}
        request_put = self.get_dummy_json_put_request(data,
            path='/chef/status/')
        request_put.POST = data
        node_api = ChefStatusResource(request_put)
        response = node_api.put()
        
        # 5 - Check if the response is valid
        self.assertEqual(response['ok'], True)
        
        self.assertNoErrorJobs()


    def test_14_search_ous_from_cga(self):
        '''
        Test 14: Search OUs from the GECOS Config Assistant
        '''
        if DISABLE_TESTS: return
        
        # 1 - Create request get all OUs
        data = {
            'q': ''
        }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/ou/gca/'
        request.GET = data
        node_api = GCAOuResource(request)
        response = node_api.get()
        
        # 2 - Check if the response is valid
        self.assertEqual(len(response['ous']),2)

        # 3 - Create request to get a specific OU
        data = {
            'q': 'OU 1'
        }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/ou/gca/'
        request.GET = data
        node_api = GCAOuResource(request)
        response = node_api.get()
        
        # 2 - Check if the response is valid
        self.assertEqual(len(response['ous']),1)

        
        self.assertNoErrorJobs()

    def test_15_jobs_search(self):
        '''
        Test 15: Execute test_08 to create jobs and after that execute
        a jobs search
        '''
        if DISABLE_TESTS: return

        self.test_08_OU()
        
        # Get jobs for this user
        data = {
            'page': 1,
            'pagesize': 30,
            'status': '',
            'archived': 'false',
            'parentId': '',
            'seeAll': 'false',
            'source': '',
            'workstation': '',
            'userfilter': ''
            }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/jobs/'
        request.GET = data
        node_api = JobResource(request)
        response = node_api.collection_get()
        self.assertEqual(response['total'], 3)
        

    def test_16_jobs_statistics(self):
        '''
        Test 16: Execute test_08 to create jobs and after that get
        the jobs statistics
        '''
        if DISABLE_TESTS: return

        self.test_08_OU()
        
        # Get jobs statistics (general)
        data = {}
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/jobs-statistics/'
        request.GET = data
        node_api = JobStatistics(request)
        response = node_api.get()
        self.assertEqual(response['processing'], 0)
        
        
        # Get jobs statistics for this user
        data = {}
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/my-jobs-statistics/'
        request.GET = data
        node_api = MyJobStatistics(request)
        response = node_api.get()
        self.assertEqual(response['processing'], 0)
        
    def test_17_node_search(self):
        '''
        Test 17: Node search
        '''
        if DISABLE_TESTS: return

        # 1 - Seach for "ou" in node name
        data = {
            'iname': 'ou',
            'search_by': 'nodename',
            'type': ''
        }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/nodes/'
        request.GET = data
        node_api = NodesResource(request)
        response = node_api.collection_get()
        self.assertEqual(response['total'], 1)
        
        # 2 - Seach for "test" in node name, for workstations and users
        data = {
            'iname': 'test',
            'search_by': 'nodename',
            'type': 'computer,user'
        }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/nodes/'
        request.GET = data
        node_api = NodesResource(request)
        response = node_api.collection_get()
        self.assertEqual(response['total'], 1)
        
        # 3 - Run other test to create a user and a workstation
        self.test_13_update_chef_status()

        # 4 - Seach for "test" in node name, for workstations and users
        data = {
            'iname': 'test',
            'search_by': 'nodename',
            'type': 'computer,user'
        }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/nodes/'
        request.GET = data
        node_api = NodesResource(request)
        response = node_api.collection_get()
        self.assertEqual(response['total'], 4)

        # 5 - Seach for "test" in node name, for workstations
        data = {
            'iname': 'test',
            'search_by': 'nodename',
            'type': 'computer'
        }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/nodes/'
        request.GET = data
        node_api = NodesResource(request)
        response = node_api.collection_get()
        self.assertEqual(response['total'], 1)
        

        # 6 - Seach for "10.35.1.16" in ip address
        data = {
            'iname': '10.35.1.16',
            'search_by': 'ip'
        }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/nodes/'
        request.GET = data
        node_api = NodesResource(request)
        response = node_api.collection_get()
        self.assertEqual(response['total'], 1)


        # 7 - Seach for "test" in username
        data = {
            'iname': 'test',
            'search_by': 'username'
        }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/nodes/'
        request.GET = data
        node_api = NodesResource(request)
        response = node_api.collection_get()
        self.assertEqual(response['total'], 1)

    def test_18_public_computers(self):
        '''
        Test 18: test public API to retrieve the list of computers.
        '''
        if DISABLE_TESTS: return

        # 1 - Run other test to create a user and a workstation
        self.test_13_update_chef_status()


        # 2 - Get list of computers
        data = { }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/computers/list/'
        request.GET = data
        node_api = ComputerPublicResource(request)
        response = node_api.get()
        self.assertEqual(len(response['computers']), 1)
        self.assertEqual(response['computers'][0]['name'], 'testing')
        

    def test_19_public_ous(self):
        '''
        Test 19: test public API to retrieve the list of ous.
        '''
        if DISABLE_TESTS: return

        # 1 - Get list of OUs
        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        
        data = { 'ou_id': str(domain_1['_id']) }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/ou/list/'
        request.GET = data
        node_api = OuPublicResource(request)
        response = node_api.get()
        self.assertEqual(len(response), 1)
        self.assertEqual(response[0]['name'], 'OU 1')
        
        
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_20_computer_CRUD(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 20: Registers a computer, updates it and deletes it
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()
        
        db = self.get_db()
        
        # 1 - Register workstation in OU and user
        chef_node_id = CHEF_NODE_ID
        self.register_computer()
        
        # Register admin
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Create and register user in chef node
        username = 'usertest'
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        
        
        # 2 - Check that the computer exists
        count = db.nodes.count_documents({'node_chef_id': chef_node_id})
        self.assertEqual(count, 1)
        
        # 3 - Update policies of the computer
        data = {'node_id': chef_node_id}
        request = self.get_dummy_request()
        request.POST = data
        computer_response = RegisterComputerResource(request)
        response = computer_response.put()
        self.assertEqual(response['ok'], True)

        # 4 - Check that the computer exists
        count = db.nodes.count_documents({'node_chef_id': chef_node_id})
        self.assertEqual(count, 1)
        
        # 5 - Delete the computer
        data = {'node_id': chef_node_id}
        request = self.get_dummy_request()
        request.GET = data
        computer_response = RegisterComputerResource(request)
        response = computer_response.delete()
        self.assertEqual(response['ok'], True)
        
        # 6 - Check that the computer does not exists
        count = db.nodes.count_documents({'node_chef_id': chef_node_id})
        self.assertEqual(count, 0)
        
        self.assertNoErrorJobs()
        

    def test_21_packages_tests(self):
        '''
        Test 21: test the API to retrieve the list of packages
        '''
        if DISABLE_TESTS: return

        # Load the packages from a small repository
        self.sync_repositories()

        # 1 - Get the package list
        data = { }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/packages/'
        request.GET = data
        package_api = PackagesResource(request)
        response = package_api.collection_get()
        self.assertTrue(response['total'] > 0)


        # 2 - Get filtered package imformation
        data = { 'package_name': 'firefox' }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/packages/'
        request.GET = data
        package_api = PackagesResource(request)
        response = package_api.collection_get()
        self.assertEqual(response['name'], 'firefox')

    def test_22_policies_tests(self):
        '''
        Test 22: test the API to retrieve the list of policies
        '''
        if DISABLE_TESTS: return

        # 1 - Get the policies list
        data = { }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/policies/'
        request.GET = data
        policies_api = PoliciesResource(request)
        response = policies_api.collection_get()
        self.assertTrue(response['total'] > 0)


    def test_23_printer_models_tests(self):
        '''
        Test 23: test the API to retrieve the list of printer models
        '''
        if DISABLE_TESTS: return
        
        # 1 - Update the printers list
        self.update_printers()

        # 2 - Get the manufacturer list
        data = { }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/printer_models/'
        request.GET = data
        policies_api = PrinterModelsResource(request)
        response = policies_api.collection_get()
        self.assertTrue(response['total'] > 0)

        # 3 - Get the models list for a manufacturer
        data = { 'manufacturer': "Lexmark"}
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/printer_models/'
        request.GET = data
        policies_api = PrinterModelsResource(request)
        response = policies_api.collection_get()
        self.assertTrue(response['total'] > 0)
        self.assertEqual(response['printer_models'][0]['manufacturer'],
                         "Lexmark")

        # 4 - Filter a model
        data = { 'manufacturer': "Lexmark", "imodel": 'B2860'}
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/printer_models/'
        request.GET = data
        policies_api = PrinterModelsResource(request)
        response = policies_api.collection_get()
        self.assertTrue(response['total'] > 0)
        self.assertTrue('B2860' in response['printer_models'][0]['model'])
        self.assertEqual(response['printer_models'][0]['manufacturer'],
                         "Lexmark")


    def test_24_service_providers_tests(self):
        '''
        Test 24: test the API to retrieve the list of broadband
        internet connection service providers.
        '''
        if DISABLE_TESTS: return
        
        # 1 - Update the ISP list
        self.update_ISP()

        # 2 - Get the service providers list
        data = { }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/serviceproviders/'
        request.GET = data
        isp_api = ServiceProvidersResource(request)
        response = isp_api.collection_get()
        self.assertTrue(response['total'] > 0)

        # 3 - Get the list of countries
        data = { 'country_list': 1 }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/serviceproviders/'
        request.GET = data
        isp_api = ServiceProvidersResource(request)
        response = isp_api.collection_get()
        self.assertTrue(response['total'] > 0)


    def test_25_session_tests(self):
        '''
        Test 25: test the API to retrieve the information about
        the user session
        '''
        if DISABLE_TESTS: return
        
        # 1 - Get information about the user session
        data = { }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/session/'
        request.GET = data
        response = session_get(request)
        self.assertEqual(response['username'], request.user['username'])


    def test_26_change_password_command(self):
        '''
        Test 26: test the command to change password
        '''
        if DISABLE_TESTS: return

        # Get previous password
        db = self.get_db()
        before = db.adminusers.find_one({'username': 'test'})
        
        # 1 - Change the password
        self.change_password_command()

        after = db.adminusers.find_one({'username': 'test'})
        
        self.assertNotEqual(before['password'], after['password'])



    def test_27_create_admin_user_command(self):
        '''
        Test 27: create admin user command test
        '''
        if DISABLE_TESTS: return

        # Check that the user doesn't exists
        db = self.get_db()
        before = db.adminusers.count_documents({'username': 'myuser'})
        self.assertEqual(before, 0)
        
        # 1 - Create the admin user
        self.create_admin_user('myuser', 'myuser@example.com')

        after = db.adminusers.count_documents({'username': 'myuser'})
        
        self.assertEqual(after, 1)



    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_28_debug_mode_expiration_command(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks,
        NodeClass, ChefNodeClass, isinstance_method):
        '''
        Test 28: debug mode expiration command test
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method)
        self.cleanErrorJobs()

        # 1 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        computer = db.nodes.find_one({'name': 'testing'})
        
        policy = db.policies.find_one({'slug': 'debug_mode_res'})
        
        # 2 - Add policy in Computer
        computer['policies'] = { str(policy['_id']): {
            'enable_debug': True,
            'expire_datetime': '2012-01-19 17:21:00'
        }}
        node_policy = self.add_and_get_policy(node=computer,
            chef_node_id=chef_node_id, api_class=ComputerResource,
            policy_path=policy['path'])
        #print(node_policy.to_dict())

        # 3 - Verification if this policy is applied in chef node
        self.assertEqual(node_policy.to_dict()['enable_debug'], True)

        # 4 - Run the command
        self.debug_mode_expiration_command('test')

        # 5 - Verify that after the expiration period the debug mode is set to
        # false
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(computer['policies'][str(policy['_id'])][
            'enable_debug'], False)



    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_29_delete_old_policies(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks,
        NodeClass, ChefNodeClass, isinstance_method):
        '''
        Test 29: delete policies that doesn't exists in the cookbook
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method)
        self.cleanErrorJobs()

        # 1 - Create a policy
        db = self.get_db()
        db.policies.insert_one({"slug": "mypolicy"})
        
        # 2 - import policies
        self.import_policies()
        
        # 3 - verify that the policy was deleted
        c = db.policies.count_documents({"slug": "mypolicy"})
        self.assertEqual(c, 0)



    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_30_test_error_generation(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 30: Test errors generated in tasks.py
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()
        
        db = self.get_db()
        
        # 1 - Register workstation in OU and user
        chef_node_id = CHEF_NODE_ID
        self.register_computer()
        
        # Register admin
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Create and register user in chef node
        username = 'usertest'
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        
        # 2 - Add a non-existent policy top the Computer
        computer = db.nodes.find_one({'name': 'testing'})
        computer['policies'] = { '000000000000000000000000': {}}
        request_put = self.get_dummy_json_put_request(computer,
            ComputerResource.schema_detail)
        node_api = ComputerResource(request_put)
        node_update = node_api.put()

        # Check that there are errors
        self.assertEqual(db.jobs.count_documents({'status': 'errors'}), 2)
        
        self.cleanErrorJobs()
        self.assertNoErrorJobs()
        
        # 3 - register the computer without policies
        # (it must fail because of the previous error)
        computer['policies'] = { }
        request_put = self.get_dummy_json_put_request(computer,
            ComputerResource.schema_detail)
        node_api = ComputerResource(request_put)
        node_update = node_api.put()
        self.assertEqual(db.jobs.count_documents({'status': 'errors'}), 2)
        
        self.cleanErrorJobs()
        self.assertNoErrorJobs()
        
        # 4 - register the computer with an actual policy
        # (it must work)
        computer = db.nodes.find_one({'name': 'testing'})
        policy = db.policies.find_one({'slug': 'debug_mode_res'})
        computer['policies'] = { str(policy['_id']): {
            'enable_debug': True,
            'expire_datetime': '2012-01-19 17:21:00'
        }}
        request_put = self.get_dummy_json_put_request(computer,
            ComputerResource.schema_detail)
        node_api = ComputerResource(request_put)
        node_update = node_api.put()
        
        self.assertNoErrorJobs()
        
        

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_31_check_obj_is_related(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 31: Create a printer and check if there is any related object
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()
        
        self.assertIsPaginatedCollection(api_class=PrinterResource)

        # 1 - Create printer
        data, new_printer = self.create_printer('Testprinter')

        # 2 - Verification that the printers has been created successfully
        self.assertEqualObjects(data, new_printer)

        # 3 - Check that there is no related object
        request = self.dummy_get_request(new_printer)
        api = PrinterResource(request)
        self.assertEqual(api.check_obj_is_related(new_printer), True)
        
        # 4 - Create a computer and add the printer policy
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        computer = db.nodes.find_one({'name': 'testing'})
        
        policy = db.policies.find_one({'slug': 'printer_can_view'})
        
        computer['policies'] = { str(policy['_id']): {
            'object_related_list': [ new_printer['_id'] ]
        }}
        node_policy = self.add_and_get_policy(node=computer,
            chef_node_id=chef_node_id, api_class=ComputerResource,
            policy_path=policy['path'])
        
        # 5 - Check that there is one related object
        self.assertEqual(api.check_obj_is_related(new_printer), False)
        

        self.assertNoErrorJobs()



    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_32_check_is_ou_empty(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 32: Create an ou and check if is empty
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()
        
        self.assertIsPaginatedCollection(api_class=PrinterResource)

        # 1 - Create an OU
        data, ou = self.create_ou('OU 2')

        # 2 - Check that the OU is empty
        request = self.dummy_get_request(ou)
        api = OrganisationalUnitResource(request)
        self.assertEqual(api.is_ou_empty(ou), True)

        # 3 - Create a printer inside the OU
        data, new_printer = self.create_printer('Testprinter', 'OU 2')
        
        # 4 - Check that the OU is not empty
        self.assertEqual(api.is_ou_empty(ou), False)
        

        self.assertNoErrorJobs()



    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_33_check_update_node(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 33: Register a computer and uses update_node method
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()
        
        self.assertIsPaginatedCollection(api_class=PrinterResource)

        # 1 - Create a computer
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 2 - Change the name in MongoDB
        computer = db.nodes.find_one({'node_chef_id': chef_node_id})
        self.assertEqual(computer['name'], 'testing' )
        
        computer['name'] = 'changed'
        db.nodes.replace_one({'node_chef_id': chef_node_id}, computer)
        computer = db.nodes.find_one({'node_chef_id': chef_node_id})
        self.assertEqual(computer['name'], 'changed' )
        
        # 3 - call the update node method
        api = ChefApiMock()
        update_node(api, chef_node_id, ou_1, db.nodes)
        
        # 4 - Check that the node name has been updated with Chef pclabel
        computer = db.nodes.find_one({'node_chef_id': chef_node_id})
        self.assertEqual(computer['name'], 'testing' )
        

        self.assertNoErrorJobs()



    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.views.portal._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_34_login_view(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext, portal_gettext,
        create_chef_admin_user_method):
        '''
        Test 34: Checks the login view
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext, create_chef_admin_user_method)
        
        portal_gettext.side_effect = gettext_mock
        
        self.cleanErrorJobs()
        
        self.assertIsPaginatedCollection(api_class=PrinterResource)

        # 1 - Register an admin user
        admin_username = 'test'

        # 2 - Try to log with a bad password
        context = None
        data = {'username': admin_username, 'password': 'bad pwd' }
        request = self.get_dummy_request(True)
        request.POST = data
        request.remote_addr = '127.0.0.1'
        request.user_agent = 'Mozilla/5.0'
        request.is_xhr = False
        view = LoginViews(context, request)
        ret = view.login()
        self.assertFalse(isinstance(ret, HTTPFound))

        # Check that the user is redirected to login
        ret = forbidden_view(context, request)
        self.assertTrue(isinstance(ret, HTTPFound))


        # 3 - Log in an admin user
        db = self.get_db()
        db.adminusers.update_one({'username': admin_username},
            {'$set': {"password" :
                "$2a$12$op45f9PEMyyRxi5iMH6/JOAJ/aIFRIR73S6CtgbXrxD/cLpnq8KRC"}}
        )
        data = {'username': admin_username, 'password': '123123' }
        request = self.get_dummy_request()
        request.POST = data
        request.remote_addr = '127.0.0.1'
        request.user_agent = 'Mozilla/5.0'
        request.is_xhr = False
        request.VERSION = '1.0.0'
        view = LoginViews(context, request)
        ret = view.login()
        self.assertTrue(isinstance(ret, HTTPFound))

        self.assertEqual(1, db.auditlog.count_documents({
            'username': admin_username,
            'action': 'login'}))

        # Check that the user is not redirected to login
        context = { 'explanation': '' }
        ret = forbidden_view(context, request)
        self.assertFalse(isinstance(ret, HTTPFound))

        # 4 - Logout
        ret = view.logout()
        self.assertTrue(isinstance(ret, HTTPFound))
        self.assertEqual(1, db.auditlog.count_documents({
            'username': admin_username,
            'action': 'logout'}))


class AdvancedTests(BaseGecosTestCase):

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_01_update_resources_user(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 1:
        1. Check the shared_folder policy works using users
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create storage
        db = self.get_db()
        data, new_storage = self.create_storage('shared folder')

        # 2 - Register workstation in OU
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # Register admin
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 3, 4 - Create and register user in chef node
        username = 'usertest'
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)

        # 5 - Add storage to user and check if it is applied in chef node
        user = db.nodes.find_one({'name': username})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        storage_policy = db.policies.find_one({'slug': 'storage_can_view'})

        user['policies'] = {text_type(storage_policy['_id']): {
            'object_related_list': [new_storage['_id']]}}
        policy_path = storage_policy['path'] + '.' + username + '.gtkbookmarks'
        node_policy = self.add_and_get_policy(node=user,
            chef_node_id=chef_node_id, api_class=UserResource,
            policy_path=policy_path)
        self.assertEqual(1, len(node_policy), 'The policy was not added!')

        # 6 - Verification if the storage is applied to user in chef node
        self.assertEqualObjects(node_policy[0], new_storage, fields=('name',
                                                                      'uri'))

        # 7 - Update storage's URI
        storage_update = self.update_node(obj=new_storage, field_name='uri',
            field_value='http://modify.storage.com', api_class=StorageResource)
        node = NodeMock(chef_node_id, None)

        # 8 - Verification that the storage has been updated successfully in 
        # chef node
        node_policy = node.attributes.get_dotted(policy_path)
        self.assertEqualObjects(node_policy[0], storage_update, fields=('name',
                                                                         'uri'))
        # 9 Create stgorage
        data, new_storage_2 = self.create_storage('shared folder mergeable')

        # 10 Add storage to OU and check if it's applied in chef node
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        ou_1['policies'] = {text_type(storage_policy['_id']): {
            'object_related_list': [new_storage_2['_id']]}}
        node_policy = self.add_and_get_policy(node=ou_1,
            chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
            policy_path=policy_path)

        # 11 - Verification if the storage is applied to user in chef node
        self.assertEmitterObjects(node_policy, [storage_update, new_storage_2],
            fields=('name', 'uri'))

        # 12 - Delete storage and verification that the storage has beed deleted
        # successfully in chef node
        node_policy = self.remove_policy_and_get_dotted(user, chef_node_id,
            UserResource, policy_path)
        self.assertEqualObjects(node_policy[0], new_storage_2, fields=('name',
                                                                        'uri'))

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_02_update_resources_workstation(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 2:
        1. Check the printer policy works using workstation
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create printer
        db = self.get_db()
        data, new_printer = self.create_printer('printer test')

        # 2 - Register workstation
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Add printer to workstation and check if it is applied in chef node
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer,
            ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()

        printer_policy = db.policies.find_one({'slug': 'printer_can_view'})
        computer['policies'] = {text_type(printer_policy['_id']): {
            'object_related_list': [new_printer['_id']]}}
        policy_path = printer_policy['path']
        node_policy = self.add_and_get_policy(node=computer,
            chef_node_id=chef_node_id, api_class=ComputerResource,
            policy_path=policy_path)

        # 4 - Verification if the printer is applied to workstation in chef node
        self.assertEqualObjects(node_policy[0], new_printer,
            fields=('oppolicy', 'model', 'uri', 'name', 'manufacturer'))

        # 5 - Modify printer's URI and check if is applied in chef node
        node = NodeMock(chef_node_id, None)
        printer_update = self.update_node(obj=new_printer, field_name='uri',
            field_value='http://modifiy.example.com', api_class=PrinterResource)
        node_policy = node.attributes.get_dotted(policy_path)

        # 6 - Verification that the printer's URI has been updated successfully
        # in chef node
        self.assertEqualObjects(node_policy[0], printer_update,
            fields=('oppolicy', 'model', 'uri', 'name', 'manufacturer'))

        # 7 - Create printer
        db = self.get_db()
        data, new_printer_2 = self.create_printer('printer mergeable')

        # 8 - Add printer to workstation and check if it is applied in chef node
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        ou_1['policies'] = {text_type(printer_policy['_id']): {
            'object_related_list': [new_printer_2['_id']]}}
        policy_path = printer_policy['path']
        node_policy = self.add_and_get_policy(node=ou_1,
            chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
            policy_path=policy_path)

        # 9 - Verification that the printer's URI has been updated successfully
        # in chef node
        self.assertEmitterObjects(node_policy, [new_printer_2, printer_update],
            fields=('oppolicy', 'model', 'uri', 'name', 'manufacturer'))

        # 10 - Delete printer and check if the chef node has been updated
        self.delete_node(printer_update, PrinterResource)
        self.assertDeleted(field_name='name', field_value='printer test')
        printer_policy = node.attributes.get_dotted(policy_path)
        self.assertEqualObjects(printer_policy[0], new_printer_2,
            fields=('oppolicy',  'model', 'uri', 'name', 'manufacturer'))
        self.assertNoErrorJobs()

    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_03_priority_ous_workstation(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks,
        NodeClass, ChefNodeClass, isinstance_method):
        '''
        Test 3:
        1. Check the registration work station works
        2. Check the policies pripority works using organisational unit
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method)
        self.cleanErrorJobs()

        # 1 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        policies = self.get_default_policies()
        for policy in policies:
            computer = db.nodes.find_one({'name': 'testing'})
            # 2 - Add policy in OU
            ou_1['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_1']}
            node_policy = self.add_and_get_policy(node=ou_1,
                chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
                policy_path=policies[policy]['path'])

            # 3 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['package_list'])
            else:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['shutdown_mode'])

            # 4 - Add policy in domain
            domain_1['policies'] = {text_type(policies[policy]['policy'][
                '_id']): policies[policy]['policy_data_node_2']}
            domain_policy = self.add_and_get_policy(node=domain_1,
                chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
                policy_path=policies[policy]['path'])

            if policies[policy]['policy']['is_mergeable']:
                # 5 - Verification if OU's and Domain's policy is applied in 
                # chef node
                self.assertEqual(domain_policy, [
                    {'action': 'add', 'name': 'gimp', 'version': 'latest'},
                    {'action': 'add', 'name': 'libreoffice',
                     'version': 'latest'}])
                # 6 - Remove OU's policy and verification if Domain's policy is 
                # applied in chef node
                policy_applied = self.remove_policy_and_get_dotted(ou_1,
                    chef_node_id, OrganisationalUnitResource,
                    policies[policy]['path'])
                self.assertEqual(policy_applied, [
                    {'action': 'add', 'name': 'libreoffice',
                     'version': 'latest'}])
                # 7 - Remove policy in domain and check if domain_1's policy 
                # isn't applied in chef node
                policy_applied = self.remove_policy_and_get_dotted(domain_1,
                    chef_node_id, OrganisationalUnitResource,
                    policies[policy]['path'])
                self.assertEqual(policy_applied, [])
                # 8, 9 - Add policy to workstation and verification if ws's 
                # policy has been applied successfully
                computer = db.nodes.find_one({'name': 'testing'})
                computer['policies'] = {text_type(policies[policy]['policy'][
                    '_id']): policies[policy]['policy_data_node_1']}
                node_policy = self.add_and_get_policy(node=computer,
                    chef_node_id=chef_node_id, api_class=ComputerResource,
                    policy_path=policies[policy]['path'])
                self.assertEqual(node_policy, [
                    {'action': 'add', 'name': 'gimp', 'version': 'latest'}])
                # 10 - Add policy in OU
                ou_1['policies'] = {text_type(policies[policy]['policy'][
                    '_id']): policies[policy]['policy_data_node_1']}
                node_policy = self.add_and_get_policy(node=ou_1,
                    chef_node_id=chef_node_id,
                    api_class=OrganisationalUnitResource,
                    policy_path=policies[policy]['path'])
                # 11 - Create workstation
                self.register_computer(
                    chef_node_id='36e13492663860e631f53a00afcsi29f')
            else:
                # 5  Verification if OU's policy is applied in chef node
                self.assertEqual(domain_policy, policies[policy][
                    'policy_data_node_1']['shutdown_mode'])
                # 6 - Remove OU's policy and verification if Domain's policy is
                # applied in chef node
                policy_applied = self.remove_policy_and_get_dotted(ou_1,
                    chef_node_id, OrganisationalUnitResource,
                    policies[policy]['path'])
                self.assertEqual(policy_applied, 'halt')
                # 7 - Remove policy in domain and check if domain_1's policy
                # isn't applied in chef node
                policy_applied = self.remove_policy_and_get_dotted(domain_1,
                    chef_node_id, OrganisationalUnitResource,
                    policies[policy]['path'])
                self.assertEqual(policy_applied, '')
                # 8, 9 - Add policy to workstation and verification if ws's
                # policy has been applied successfully
                computer['policies'] = {text_type(policies[policy]['policy'][
                    '_id']): policies[policy]['policy_data_node_1']}
                node_policy = self.add_and_get_policy(node=computer,
                    chef_node_id=chef_node_id, api_class=ComputerResource,
                    policy_path=policies[policy]['path'])
                self.assertEqual(node_policy, 'reboot')
                # 10 - Add policy in OU
                ou_1['policies'] = {text_type(policies[policy]['policy'][
                    '_id']): policies[policy]['policy_data_node_1']}
                node_policy = self.add_and_get_policy(node=ou_1,
                    chef_node_id=chef_node_id,
                    api_class=OrganisationalUnitResource,
                    policy_path=policies[policy]['path'])
                # 11 - Create workstation
                self.register_computer(
                    chef_node_id='36e13492663860e631f53a023fcsi29f')
            # 3 - Verification that the OU's policy has been applied
            # successfully
            if policies[policy]['policy']['is_mergeable']:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['package_list'])
            else:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['shutdown_mode'])

        self.assertNoErrorJobs()


    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_04_priority_user_workstation(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 4:
        1. Check the registration work station works
        2. Check the policies priority works using organisational unit and user
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 1 - Create user
        username = 'testuser'
        data, new_user = self.create_user(username)
        self.assertEqualObjects(data, new_user)

        # 2 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Register user in ws
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)

        policies = self.get_default_policies_user()
        user = db.nodes.find_one({'name': username})
        for policy in policies:
            # 4 - Add policy in OU
            ou_1['policies'] = {text_type(policies[policy]['policy']['_id']): 
                                policies[policy]['policy_data_node_1']}
            name_element_policy = policies[policy]['policy_data_node_1']
            policy_path_1 = policies[policy]['path'] + username + '.' + list(
                name_element_policy.keys())[0]
            node_policy = self.add_and_get_policy(node=ou_1,
                chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
                policy_path=policy_path_1)
            # 5 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['desktops'])
            else:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['desktop_file'])
            # 6 - Add policy in user
            name_element_policy = policies[policy]['policy_data_node_2']
            policy_path_2 = policies[policy]['path'] + username + '.' + list(
                name_element_policy.keys())[0]
            user['policies'] = {text_type(policies[policy]['policy']['_id']): 
                policies[policy]['policy_data_node_2']}
            node_policy = self.add_and_get_policy(node=user,
                chef_node_id=chef_node_id, api_class=UserResource,
                policy_path=policy_path_2)

            if policies[policy]['policy']['is_mergeable']:
                # 7 - Verification if this policy is applied in chef node
                self.assertEqual(node_policy, [
                    {'name': 'kate', 'action': 'add'},
                    {'name': 'sublime', 'action': 'add'}])
            else:
                # 7 - Verification if this policy is applied in chef node
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_2']['desktop_file'])
            # Remove policy in OU
            self.remove_policy_and_get_dotted(ou_1, chef_node_id,
                OrganisationalUnitResource, policy_path_1)

        # 8, 9 - Create user Assign user to workstation
        username = 'usertest'
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})

        for policy in policies:
            # 10 - Add policy in user
            name_element_policy = policies[policy]['policy_data_node_2']
            policy_path_2 = policies[policy]['path'] + username + '.' + list(
                name_element_policy.keys())[0]
            user['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_2']}
            node_policy = self.add_and_get_policy(node=user,
                chef_node_id=chef_node_id, api_class=UserResource,
                policy_path=policy_path_2)

            if policies[policy]['policy']['is_mergeable']:
                # 11 - Verification if this policy is applied in chef node
                self.assertEqual(node_policy, [
                    {'name': 'sublime', 'action': 'add'}])
            else:
                # 11 - Verification if this policy is applied in chef node
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_2']['desktop_file'])
            # 12 - Add policy in OU
            ou_1['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_1']}
            name_element_policy = policies[policy]['policy_data_node_1']
            policy_path_1 = policies[policy]['path'] + username + '.' + list(
                name_element_policy.keys())[0]
            node_policy = self.add_and_get_policy(node=ou_1,
                chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
                policy_path=policy_path_1)
            if policies[policy]['policy']['is_mergeable']:
                # 13 - Verification if this policy is applied in chef node
                node = NodeMock(chef_node_id, None)
                node_policy = node.attributes.get_dotted(policy_path_1)
                self.assertEqual(node_policy, [
                    {'name': 'kate', 'action': 'add'},
                    {'name': 'sublime', 'action': 'add'}])
            else:
                # 13 - Verification if this policy is applied in chef node
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_2']['desktop_file'])

        self.assertNoErrorJobs()


    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_05_priority_workstation_ous_groups(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 5:
        1. Check the registration work station works
        2. Check the policies priority works using organisational unit and
           groups
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1- Create a group
        data, new_group = self.create_group('testgroup')

        # 2 - Register a workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()
        computer = db.nodes.find_one({'name': 'testing'})

        # 3 - Assign group to computer
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': 'testgroup'})
        self.assertEqual(group['members'][0], computer['_id'])

        policies = self.get_default_policies()
        for policy in policies:
            # 4 - Add policy in OU
            ou_1['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_1']}
            node_policy = self.add_and_get_policy(node=ou_1,
                chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
                policy_path=policies[policy]['path'])

            # 5 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['package_list'])
            else:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['shutdown_mode'])

            # 6 -  Add policy in group
            group['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_2']}
            node_policy = self.add_and_get_policy(node=group,
                chef_node_id=chef_node_id, api_class=GroupResource,
                policy_path=policies[policy]['path'])

            if policies[policy]['policy']['is_mergeable']:
                # 7 - Verification if the policy is applied in chef node
                self.assertItemsEqual(node_policy, [
                    {'name': 'libreoffice', 'version': 'latest',
                        'action': 'add'},
                    {'name': 'gimp', 'version': 'latest', 'action': 'add'}])
                # 8 - Remove policy in group
                policy_applied = self.remove_policy_and_get_dotted(group,
                    chef_node_id, GroupResource, policies[policy]['path'])

                # 9 - Verification if the OU's policy is applied in chef node
                self.assertItemsEqual(policy_applied,
                    [{'name': 'gimp', 'version': 'latest', 'action': 'add'}])
            else:
                # 7 - Verification if the policy is applied in chef node
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_2']['shutdown_mode'])

                # 8 - Remove policy in group
                policy_applied = self.remove_policy_and_get_dotted(group,
                    chef_node_id, GroupResource, policies[policy]['path'])

                # 9 - Verification if the OU's policy is applied in chef node
                self.assertEqual(policy_applied, 'reboot')

        self.assertNoErrorJobs()


    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_06_priority_workstation_groups(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 6:
        1. Check the registration work station works
        2. Check the policies priority works using workstation and groups
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create A group
        data, new_group_a = self.create_group('group_A')

        # 2 - Create B group
        data, new_group_b = self.create_group('group_B')

        # 3 - Register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()
        computer = db.nodes.find_one({'name': 'testing'})

        # 4 - Assign groupA to computer
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group_a)

        # 5 - Assign groupB to computer
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group_b)

        # Check if group's node is update in node chef
        group_a = db.nodes.find_one({'name': 'group_A'})
        self.assertEqual(group_a['members'][0], computer['_id'])
        group_b = db.nodes.find_one({'name': 'group_B'})
        self.assertEqual(group_b['members'][0], computer['_id'])

        policies = self.get_default_policies()
        for policy in policies:
            # 6 - Add policy in A group
            group_a['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_1']}
            group_a_policy = self.add_and_get_policy(node=group_a,
                chef_node_id=chef_node_id, api_class=GroupResource,
                policy_path=policies[policy]['path'])

            # 7 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEqual(group_a_policy, policies[policy][
                    'policy_data_node_1']['package_list'])
            else:
                self.assertEqual(group_a_policy, policies[policy][
                    'policy_data_node_1']['shutdown_mode'])

            # 8 -  Add policy in B group
            group_b['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_2']}
            group_b_policy = self.add_and_get_policy(node=group_b,
                chef_node_id=chef_node_id, api_class=GroupResource,
                policy_path=policies[policy]['path'])
            if policies[policy]['policy']['is_mergeable']:
                # 9 - Verification if the policy is applied in chef node
                self.assertItemsEqual(group_b_policy, [
                    {'name': 'libreoffice', 'version': 'latest',
                        'action': 'add'}, 
                    {'name': 'gimp', 'version': 'latest', 'action': 'add'}])
                # 10 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a,
                    chef_node_id, GroupResource, policies[policy]['path'])

                # 11 - Verification if the B group's policy is applied in chef
                # node
                self.assertItemsEqual(policy_applied, [
                    {'name': 'libreoffice', 'version': 'latest',
                        'action': 'add'}])
            else:
                # 9 - Verification if the policy is applied in chef node
                self.assertEqual(group_b_policy,
                    policies[policy]['policy_data_node_2']['shutdown_mode'])

                # 10 - Remove policy in B group
                policy_applied = self.remove_policy_and_get_dotted(group_b,
                    chef_node_id, GroupResource, policies[policy]['path'])

                # 11 - Verification if the A group's policy is applied in chef
                # node
                self.assertEqual(policy_applied, 'reboot')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_07_priority_workstation_groups_different_ou(self,
        get_chef_api_method, get_cookbook_method, get_cookbook_method_tasks,
        NodeClass, ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 7:
        1. Check the registration work station works
        2. Check the policies priority works using groups in differents OUs
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create A group
        data, new_group_a = self.create_group('group_A')

        # 2 - Create B group
        data, new_group_b = self.create_group('group_B', ou_name='Domain 1')

        # 3 - Register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()
        computer = db.nodes.find_one({'name': 'testing'})

        # 4 - Assign groupA to computer
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group_a)

        # 5 - Assign groupB to computer
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group_b)

        # Check if group's node is update in node chef
        group_a = db.nodes.find_one({'name': new_group_a['name']})
        self.assertEqual(group_a['members'][0], computer['_id'])
        group_b = db.nodes.find_one({'name': new_group_b['name']})
        self.assertEqual(group_b['members'][0], computer['_id'])

        policies = self.get_default_policies()
        for policy in policies:
            # 6 - Add policy in A group
            group_a['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_1']}
            group_a_policy = self.add_and_get_policy(node=group_a,
                chef_node_id=chef_node_id, api_class=GroupResource,
                policy_path=policies[policy]['path'])

            # 7 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEqual(group_a_policy, policies[policy][
                    'policy_data_node_1']['package_list'])
            else:
                self.assertEqual(group_a_policy, policies[policy][
                    'policy_data_node_1']['shutdown_mode'])

            # 8 -  Add policy in B group
            group_b['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_2']}
            group_b_policy = self.add_and_get_policy(node=group_b,
                chef_node_id=chef_node_id, api_class=GroupResource,
                policy_path=policies[policy]['path'])
            if policies[policy]['policy']['is_mergeable']:
                # 9 - Verification if the policy is applied in chef node
                self.assertItemsEqual(group_b_policy, [
                    {'name': 'libreoffice', 'version': 'latest',
                        'action': 'add'},
                    {'name': 'gimp', 'version': 'latest', 'action': 'add'}])
                # 10 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a,
                    chef_node_id, GroupResource, policies[policy]['path'])

                # 11 - Verification if the B group's policy is applied in chef
                # node
                self.assertItemsEqual(policy_applied, [
                    {'name': 'libreoffice', 'version': 'latest',
                     'action': 'add'}])
            else:
                # 9 - Verification if the policy is applied in chef node
                self.assertEqual(group_b_policy, policies[policy][
                    'policy_data_node_1']['shutdown_mode'])

                # 10 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a,
                    chef_node_id, GroupResource, policies[policy]['path'])

                # 11 - Verification if the B group's policy is applied in chef
                # node
                self.assertEqual(policy_applied, 'halt')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_08_priority_user_ous_groups(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 8:
        1. Check the registration work station works
        2. Check the policies priority works using groups and OUs
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create a group
        data, new_group = self.create_group('group_test')

        # 2 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 3, 4 - Register user in chef node and register user in chef node
        username = 'testuser'
        self.create_user(username)  
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)

        # 5 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], user['_id'])

        policies = self.get_default_policies_user()
        for policy in policies:
            # 6 - Add policy in OU
            ou_1['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_1']}
            name_element_policy = policies[policy]['policy_data_node_1']
            policy_path_1 = policies[policy]['path'] + username + '.' + list(
                name_element_policy.keys())[0]
            node_policy = self.add_and_get_policy(node=ou_1,
                chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
                policy_path=policy_path_1)

            # 7 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['desktops'])
            else:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['desktop_file'])

            # 8 -  Add policy in group
            group['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_2']}
            name_element_policy = policies[policy]['policy_data_node_2']
            policy_path_2 = policies[policy]['path'] + username + '.' + list(
                name_element_policy.keys())[0]            
            node_policy = self.add_and_get_policy(node=group,
                chef_node_id=chef_node_id, api_class=GroupResource,
                policy_path=policy_path_2)

            if policies[policy]['policy']['is_mergeable']:
                # 9 - Verification if the policy is applied in chef node
                self.assertItemsEqual(node_policy, [
                    {'name': 'kate', 'action': 'add'},
                    {'name': 'sublime', 'action': 'add'}])
                # 10 - Remove policy in group
                policy_applied = self.remove_policy_and_get_dotted(group,
                    chef_node_id, GroupResource, policy_path_1)

                # 11 - Verification if the OU's policy is applied in chef node
                self.assertItemsEqual(policy_applied,
                    [{'name': 'kate', 'action': 'add'}])
            else:
                # 9 - Verification if the policy is applied in chef node
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_2']['desktop_file'])

                # 10 - Remove policy in group
                policy_applied = self.remove_policy_and_get_dotted(group,
                    chef_node_id, GroupResource, policy_path_1)

                # 11 - Verification if the OU's policy is applied in chef node
                self.assertEqual(policy_applied, 'mountain.png')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_09_priority_user_groups_same_ou(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 9:
        1. Check the registration work station works
        2. Check the policies priority works using groups in the same OU
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create A group
        data, new_group_a = self.create_group('group_A')

        # 2 - Create B group
        data, new_group_b = self.create_group('group_B', ou_name='Domain 1')

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 3 - Register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 4, 5 - Register user in chef node
        username = 'testuser'
        self.create_user(username)  
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)

        # 6 - Assign A group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group_a)

        # 7 - Assign B group to user
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group_b)

        # Check if group's node is update in node chef
        group_a = db.nodes.find_one({'name': new_group_a['name']})
        self.assertEqual(group_a['members'][0], user['_id'])
        group_b = db.nodes.find_one({'name': new_group_b['name']})
        self.assertEqual(group_b['members'][0], user['_id'])

        policies = self.get_default_policies_user()
        for policy in policies:
            # 8 - Add policy in A group
            group_a['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_1']}
            name_element_policy = policies[policy]['policy_data_node_1']
            policy_path_1 = policies[policy]['path'] + username + '.' + list(
                name_element_policy.keys())[0]
            group_a_policy = self.add_and_get_policy(node=group_a,
                chef_node_id=chef_node_id, api_class=GroupResource,
                policy_path=policy_path_1)

            # 9 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertItemsEqual(group_a_policy, policies[policy][
                    'policy_data_node_1']['desktops'])
            else:
                self.assertEqual(group_a_policy, policies[policy][
                    'policy_data_node_1']['desktop_file'])

            # 10 -  Add policy in B group
            group_b['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_2']}
            name_element_policy = policies[policy]['policy_data_node_2']
            policy_path_2 = policies[policy]['path'] + username + '.' + list(
                name_element_policy.keys())[0]            
            group_b_policy = self.add_and_get_policy(node=group_b,
                chef_node_id=chef_node_id, api_class=GroupResource,
                policy_path=policy_path_2)
            if policies[policy]['policy']['is_mergeable']:
                # 11 - Verification if the policy is applied in chef node
                self.assertItemsEqual(group_b_policy, [
                    {"name": "kate", "action": "add"},
                    {"name": "sublime", "action": "add"}])
                # 12 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a,
                    chef_node_id, GroupResource, policy_path_1)

                # 13 - Verification if the B group's policy is applied in chef
                # node
                self.assertEqual(policy_applied, [
                    {"name": "sublime", "action": "add"}])
            else:
                # 11 - Verification if the policy is applied in chef node
                self.assertEqual(group_b_policy, policies[policy][
                    'policy_data_node_1']['desktop_file'])

                # 12 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a,
                    chef_node_id, GroupResource, policy_path_1)

                # 13 - Verification if the B group's policy is applied in chef
                # node
                self.assertEqual(policy_applied, 'river.png')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_10_priority_user_groups_different_ou(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 10:
        1. Check the registration work station works
        2. Check the policies priority works using groups in differents OUs
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create A group
        data, new_group_a = self.create_group('group_A')

        # 1 - Create B group
        data, new_group_b = self.create_group('group_B', ou_name='Domain 1')

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 3 - Register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 4, 5 - Register user in chef node
        username = 'testuser'
        self.create_user(username)  
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)

        # 6 - Assign A group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group_a)

        # 7  - Assign B group to user
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group_b)

        # Check if group's node is update in node chef
        group_a = db.nodes.find_one({'name': new_group_a['name']})
        self.assertEqual(group_a['members'][0], user['_id'])
        group_b = db.nodes.find_one({'name': new_group_b['name']})
        self.assertEqual(group_b['members'][0], user['_id'])

        policies = self.get_default_policies_user()
        for policy in policies:
            # 8 - Add policy in A group
            group_a['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_1']}
            name_element_policy = policies[policy]['policy_data_node_1']
            policy_path_1 = policies[policy]['path'] + username + '.' + list(
                name_element_policy.keys())[0]            
            group_a_policy = self.add_and_get_policy(node=group_a,
                chef_node_id=chef_node_id, api_class=GroupResource,
                policy_path=policy_path_1)

            # 9 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertItemsEqual(group_a_policy, policies[policy][
                    'policy_data_node_1']['desktops'])
            else:
                self.assertEqual(group_a_policy, policies[policy][
                    'policy_data_node_1']['desktop_file'])

            # 10 -  Add policy in B group
            group_b['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_2']}
            name_element_policy = policies[policy]['policy_data_node_2']
            policy_path_2 = policies[policy]['path'] + username + '.' + list(
                name_element_policy.keys())[0]            
            group_b_policy = self.add_and_get_policy(node=group_b,
                chef_node_id=chef_node_id, api_class=GroupResource,
                policy_path=policy_path_2)
            if policies[policy]['policy']['is_mergeable']:
                # 11 - Verification if the policy is applied in chef node
                self.assertItemsEqual(group_b_policy, [
                    {"name": "kate", "action": "add"},
                    {"name": "sublime", "action": "add"}])
                # 12 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a,
                    chef_node_id, GroupResource, policy_path_1)

                # 13 - Verification if the B group's policy is applied in chef
                # node
                self.assertItemsEqual(policy_applied, [
                    {"name": "sublime", "action": "add"}])
            else:
                # 11 - Verification if the policy is applied in chef node
                self.assertEqual(group_b_policy, policies[policy][
                    'policy_data_node_1']['desktop_file'])

                # 12 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a,
                    chef_node_id, GroupResource, policy_path_1)

                # 13 - Verification if the B group's policy is applied in chef
                # node
                self.assertEqual(policy_applied, 'river.png')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_11_move_workstation(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 11:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 2 - Add policy in OU
        package_res_policy = self.get_default_ws_policy()
        policy_path = package_res_policy['path'] + '.package_list'
        ou_1['policies'] = {text_type(package_res_policy['_id']): {
            'package_list': [
                {'name': 'gimp', 'version': 'latest', 'action': 'add'}]}}
        package_res_node_policy = self.add_and_get_policy(node=ou_1,
            chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
            policy_path=policy_path)

        # 3 - Verification if this policy is applied in chef node
        self.assertItemsEqual(package_res_node_policy, [
            {'name': 'gimp', 'version': 'latest', 'action': 'add'}])

        # 4 - Add policy in domain
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        domain_1['policies'] = {text_type(package_res_policy['_id']): {
            'package_list': [
                {'name': 'libreoffice', 'version': 'latest', 'action': 'add'}]}}
        package_res_domain_policy = self.add_and_get_policy(node=domain_1,
            chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
            policy_path=policy_path)

        # 5 - Verification if the OU's policy is applied in chef node
        self.assertItemsEqual(package_res_domain_policy, [
            {'name': 'gimp', 'version': 'latest', 'action': 'add'}, 
            {'name': 'libreoffice', 'version': 'latest', 'action': 'add'}])

        # 6 - Move workstation to domain_1
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer,
            ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()
        self.assertNoErrorJobs()
        self.update_node(obj=computer,
                         field_name='path',
                         field_value=ou_1['path'],
                         api_class=ComputerResource)
        # 7 - Verification if domain_1's policy is applied in chef node
        node = NodeMock(chef_node_id, None)
        package_list = node.attributes.get_dotted(policy_path)
        self.assertItemsEqual(package_list, [
            {'name': 'libreoffice', 'version': 'latest', 'action': 'add'}])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_12_move_user(self, get_chef_api_method, get_cookbook_method,
        get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
        gettext, create_chef_admin_user_method):
        '''
        Test 12:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 2, 3 - Register user in chef node
        username = 'testuser'
        self.create_user(username)  
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)

        # 4 - Add policy in OU
        user_launcher_policy = self.get_default_user_policy()
        policy_path = user_launcher_policy['path'] + '.users.' + username + \
            '.launchers'
        ou_1['policies'] = {text_type(user_launcher_policy['_id']): {
            'launchers': ['OUsLauncher']}}
        node_policy = self.add_and_get_policy(node=ou_1,
            chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
            policy_path=policy_path)

        # 5 - Verification if this policy is applied in chef node
        self.assertEqual(node_policy, ['OUsLauncher'])

        # 6 - Add policy in domain
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        domain_1['policies'] = {text_type(user_launcher_policy['_id']): {
            'launchers': ['DomainLauncher']}}
        self.add_and_get_policy(node=domain_1, chef_node_id=chef_node_id,
            api_class=OrganisationalUnitResource, policy_path=policy_path)

        # 7 - Verification if the OU's policy is applied in chef node
        self.assertEqual(node_policy, ['OUsLauncher'])

        # 8 - Move user to domain_1
        user = db.nodes.find_one({'name': username})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        self.update_node(obj=user,
                         field_name='path',
                         field_value=ou_1['path'],
                         api_class=UserResource)

        # 9 - Verification if domain_1's policy is applied in chef node
        node = NodeMock(chef_node_id, None)
        package_list = node.attributes.get_dotted(policy_path)
        self.assertEqual(package_list, ['DomainLauncher'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')
    def test_13_group_visibility(self, get_chef_api_method, get_cookbook_method,
        get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
        gettext, create_chef_admin_user_method):
        '''
        Test 13:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create group in OU
        data, new_group = self.create_group('group_test')

        # Create a workstation in Domain
        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer(ou_name=domain_1['name'])

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 2 - Register user in chef node
        username = 'testuser'
        self.create_user(username, ou_name=domain_1['name'])  
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)

        # 3 -Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group)
        user = db.nodes.find_one({'name': username})

        # 4 - Verification that the user can't be assigned to group
        self.assertEqual(user['memberof'], [])

        # 5 - Create group in Domain
        data, new_group_b = self.create_group('group_B', ou_name='Domain 1')

        # 6 - Assign group to user
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group_b)
        user = db.nodes.find_one({'name': username})

        # 7 - Verification that the user has been assigned to user successfully
        self.assertEqual(user['memberof'][0], ObjectId(new_group_b['_id']))

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_14_printer_visibility(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 14:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create a group in OU
        data, new_group = self.create_group('group_test')

        # Create printer in other OU
        data, new_ou = self.create_ou('OU 2')
        self.assertEqualObjects(data, new_ou)
        data, new_printer = self.create_printer('printer test', 'OU 2')

        # Create a workstation in OU
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # Assign group to computer
        computer = db.nodes.find_one({'name': 'testing'})
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group)

        computer = db.nodes.find_one({'name': computer['name']})
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])

        # 3, 4 - Add printer to group and check if it is applied in chef node
        printer_policy = db.policies.find_one({'slug': 'printer_can_view'})
        group['policies'] = {text_type(printer_policy['_id']): {
            'object_related_list': [new_printer['_id']]}}
        policy_path = printer_policy['path']
        printer_policy = self.add_and_get_policy(node=group,
            chef_node_id=chef_node_id, api_class=GroupResource,
            policy_path=policy_path)
        self.assertEqual(printer_policy, [])

        # 5 - Create printer
        data, new_printer_ou = self.create_printer('printer OU')

        # 6, 7 - Add printer to group and check if it is applied in chef node
        printer_policy = db.policies.find_one({'slug': 'printer_can_view'})
        group['policies'] = {text_type(printer_policy['_id']): {
            'object_related_list': [new_printer_ou['_id']]}}
        policy_path = printer_policy['path']
        printer_policy = self.add_and_get_policy(node=group,
            chef_node_id=chef_node_id, api_class=GroupResource,
            policy_path=policy_path)
        self.assertEqualObjects(printer_policy[0],
            new_printer_ou, fields=('oppolicy', 'model', 'uri', 'name',
                                    'manufacturer'))

        node = NodeMock(chef_node_id, None)
        node.attributes.get_dotted(policy_path)

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_15_shared_folder_visibility(self, get_chef_api_method, 
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 15:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create a group in OU
        data, new_group = self.create_group('group_test')

        # Create new OU
        data, new_ou = self.create_ou('OU 2')
        self.assertEqualObjects(data, new_ou)

        # 2 - Create a storage
        data, new_storage = self.create_storage('shared folder', new_ou['name'])

        # Create a workstation in OU
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Register user in chef node
        username = 'testuser'
        self.create_user(username)  
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group)

        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], user['_id'])

        # 3, 4 - Add printer to group and check if it is applied in chef node
        storage_policy = db.policies.find_one({'slug': 'storage_can_view'})
        group['policies'] = {text_type(storage_policy['_id']): {
            'object_related_list': [new_storage['_id']]}}
        policy_path = storage_policy['path'] + '.' + username + '.gtkbookmarks'
        storage_policy = self.add_and_get_policy(node=group,
            chef_node_id=chef_node_id, api_class=GroupResource,
            policy_path=policy_path)
        self.assertEqual(storage_policy, [])

        # 5 - Create a storage
        data, new_storage_ou = self.create_storage('shared_folder_ou')

        # 6,7 - Add printer to group and check if it is applied in chef node
        storage_policy = db.policies.find_one({'slug': 'storage_can_view'})
        group['policies'] = {text_type(storage_policy['_id']): {
            'object_related_list': [new_storage_ou['_id']]}}
        storage_policy = self.add_and_get_policy(node=group,
            chef_node_id=chef_node_id, api_class=GroupResource,
            policy_path=policy_path)
        self.assertEqualObjects(storage_policy[0], new_storage_ou,
            fields=('name', 'uri'))
        node = NodeMock(chef_node_id, None)
        node.attributes.get_dotted(policy_path)

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_16_repository_visibility(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 16:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create a group in OU
        data, new_group = self.create_group('group_test')

        # Create new OU
        data, new_ou = self.create_ou('OU 2')
        self.assertEqualObjects(data, new_ou)

        # 2 - Create a repository
        data, new_repository = self.create_repository('repo_ou2',
            new_ou['name'])

        # Create a workstation in OU
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Register user in chef node
        username = 'testuser'
        self.create_user(username)  
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group)

        group = db.nodes.find_one({'name': 'group_test'})
        self.assertEqual(group['members'][0], computer['_id'])

        # 3, 4 - Add repository to group and check if it is applied in chef node
        storage_policy = db.policies.find_one({'slug': 'repository_can_view'})
        group['policies'] = {text_type(storage_policy['_id']): {
            'object_related_list': [new_repository['_id']]}}
        policy_path = storage_policy['path']
        node_policy = self.add_and_get_policy(node=group,
            chef_node_id=chef_node_id, api_class=GroupResource,
            policy_path=policy_path)
        self.assertEqual(node_policy, [])

        # 5 - Create a repository
        data, new_repository_ou = self.create_repository('repo_ou')

        # 6, 7 - Add repository to group and check if it is applied in chef node
        group['policies'] = {text_type(storage_policy['_id']): {
            'object_related_list': [new_repository_ou['_id']]}}
        node_policy = self.add_and_get_policy(node=group,
            chef_node_id=chef_node_id, api_class=GroupResource,
            policy_path=policy_path)
        self.assertEqualObjects(node_policy[0], new_repository_ou,
            fields=('key_server', 'uri', 'components', 'repo_key', 'deb_src'))
        # 8 - Create a repository
        data, new_repository_ou_2 = self.create_repository('repo_ou_mergeable')

        # 9, 10 - Add repository to group and check if it is applied in chef
        # node
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        ou_1['policies'] = {text_type(storage_policy['_id']): {
            'object_related_list': [new_repository_ou_2['_id']]}}
        node_policy = self.add_and_get_policy(node=ou_1,
            chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
            policy_path=policy_path)

        self.assertEmitterObjects(node_policy,
            [new_repository_ou, new_repository_ou_2],
            fields=('key_server', 'uri', 'components', 'repo_key', 'deb_src'))

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_17_delete_ou_with_workstation_and_user_in_domain(self,
        get_chef_api_method, get_cookbook_method, get_cookbook_method_tasks,
        NodeClass, ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method, TaskNodeClass, TaskClientClass):
        '''
        Test 17:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method,
            None, TaskNodeClass, TaskClientClass)
        self.cleanErrorJobs()

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 1 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 2 - Create user in domain
        username = 'testuser'
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        data, new_user = self.create_user(username, domain_1['name'])

        # 3 - Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})

        # 4 - Verification that the user has been registered successfully
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Delete OU
        self.delete_node(ou_1, OrganisationalUnitResource)
        self.assertDeleted(field_name='name', field_value=ou_1['name'])

        # 6, 7 - Verification that the OU and worskstation have been deleted
        # successfully
        ou_1 = db.nodes.find_one({'name': ou_1['name']})
        computer = db.nodes.find_one({'name': computer['name']})
        self.assertIsNone(ou_1)
        self.assertIsNone(computer)

        # 8 - Verification that the workstation has been deleted from user
        user = db.nodes.find_one({'name': username})
        self.assertEqual(NODES, {})
        self.assertEqual(user['computers'], [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_18_delete_ou_with_user_and_workstation_in_domain(self,
        get_chef_api_method, get_cookbook_method, get_cookbook_method_tasks,
        NodeClass, ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method, TaskNodeClass, TaskClientClass):
        '''
        Test 18:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method,
            TaskNodeClass, TaskClientClass)
        self.cleanErrorJobs()

        TaskNodeClass.side_effect = NodeMock
        TaskClientClass.side_effect = ClientMock

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 1 - Create a workstation in Domain
        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer(ou_name=domain_1['name'])

        # 2 - Create user in OU
        username = 'testuser'
        data, new_user = self.create_user(username)

        # 3, 4 - Register user in chef node and verify it
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Add policy in user and check if this policy is applied in chef node
        user_launcher_policy = self.get_default_user_policy()
        policy_path = user_launcher_policy['path'] + '.users.' + username + \
             '.launchers'
        user_policy = db.nodes.find_one({'name': username})
        user_policy['policies'] = {text_type(user_launcher_policy['_id']): {
            'launchers': ['UserLauncher']}}
        user_policy = self.add_and_get_policy(node=user_policy,
            chef_node_id=chef_node_id, api_class=UserResource,
            policy_path=policy_path)
        self.assertEqual(user_policy, ['UserLauncher'])

        # 6 - Delete OU
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        self.delete_node(ou_1, OrganisationalUnitResource)

        # 7 - Verification if the OU has been deleted successfully
        self.assertDeleted(field_name='name', field_value=ou_1['name'])

        # 8 - Verification if the user has been deleted successfully
        ou_1 = db.nodes.find_one({'name': ou_1['name']})
        user = db.nodes.find_one({'name': username})
        self.assertIsNone(ou_1)
        self.assertIsNone(user)

        # 9 - Verification if the policy has been deleted from node chef
        node = NodeMock(chef_node_id, None)
        try:
            package_list = node.attributes.get_dotted(policy_path)
        except KeyError:
            package_list = None

        self.assertIsNone(package_list)
        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_19_delete_ou_with_group(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method, TaskNodeClass, TaskClientClass):
        '''
        Test 19:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method,
            None, TaskNodeClass, TaskClientClass)
        self.cleanErrorJobs()

        # 1 - Create a group
        data, new_group = self.create_group('testgroup')

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 2 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Create user in OU
        username = 'usertest'
        data, new_user = self.create_user(username)

        # 4 - Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Assign group to computer
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group)
        computer = db.nodes.find_one({'name': computer['name']})

        # 6 - Verification if the group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])

        # 7 - Delete OU
        self.delete_node(ou_1, OrganisationalUnitResource)
        self.assertDeleted(field_name='name', field_value='OU 1')

        # 8, 9 - Verification if the OU, workstation, group and user have been
        # deleted successfully
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        user = db.nodes.find_one({'name': username})
        group = db.nodes.find_one({'name': new_group['name']})
        workstation = db.nodes.find_one({'name': computer['name']})
        self.assertIsNone(ou_1)
        self.assertIsNone(user)
        self.assertIsNone(group)
        self.assertIsNone(workstation)
        self.assertEqual(NODES, {})

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_20_delete_group_with_workstation_and_user(self,
        get_chef_api_method, get_cookbook_method, get_cookbook_method_tasks,
        NodeClass, ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method, TaskNodeClass, TaskClientClass):
        '''
        Test 20:
        1. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method,
            None, TaskNodeClass, TaskClientClass)
        self.cleanErrorJobs()

        # 1 - Create a group
        data, new_group = self.create_group('testgroup')

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 2 - Register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Create user in OU
        username = 'usertest'
        data, new_user = self.create_user(username)

        # 4 - Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Assign group to computer
        computer = db.nodes.find_one({'name': computer['name']})
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group)

        # 6 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group)

        # 7 - Check if group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])
        self.assertEqual(group['members'][1], user['_id'])

        # 8 - Delete group
        self.delete_node(group, GroupResource)
        self.assertDeleted(field_name='name', field_value=new_group['name'])

        # 9 - Verification if the groups has been deleted successfully from chef
        # node, user and workstation.
        user = db.nodes.find_one({'name': username})
        group = db.nodes.find_one({'name': new_group['name']})
        workstation = db.nodes.find_one({'name': computer['name']})
        self.assertIsNone(group)
        self.assertEqual(workstation['memberof'], [])
        self.assertEqual(user['memberof'], [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_21_delete_group_with_politic(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method, TaskNodeClass, TaskClientClass):
        '''
        Test 21:
        1. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method,
            None, TaskNodeClass, TaskClientClass)
        self.cleanErrorJobs()

        # 1 - Create a group
        data, new_group = self.create_group('testgroup')

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 2 - Register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Create user in OU
        username = 'usertest'
        data, new_user = self.create_user(username)

        # 4 - Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Assign group to computer
        computer = db.nodes.find_one({'name': computer['name']})
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group)

        # 6 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])
        self.assertEqual(group['members'][1], user['_id'])

        # 7, 8 - Add policy in Group and check if this policy is applied in chef
        # node
        group_launcher_policy = self.get_default_user_policy()
        policy_path = group_launcher_policy['path'] + '.users.' + username + \
             '.launchers'
        group['policies'] = {text_type(group_launcher_policy['_id']): {
            'launchers': ['OUsLauncher']}}
        node_policy = self.add_and_get_policy(node=group,
            chef_node_id=chef_node_id, api_class=GroupResource,
            policy_path=policy_path)
        self.assertEqual(node_policy, ['OUsLauncher'])

        # 9 - Delete group
        self.delete_node(group, GroupResource)
        self.assertDeleted(field_name='name', field_value=new_group['name'])

        # 10 - Verification if the policy has been deleted from chef node
        node = NodeMock(chef_node_id, None)
        try:
            launchers = node.attributes.get_dotted(policy_path)
        except KeyError:
            launchers = None

        self.assertIsNone(launchers)

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_22_delete_group_in_domain_with_politic(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method, TaskNodeClass, TaskClientClass):
        '''
        Test 22:
        1. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method,
            None, TaskNodeClass, TaskClientClass)
        self.cleanErrorJobs()

        # 1 - Create a group
        data, new_group = self.create_group('testgroup', ou_name='Domain 1')

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 2 - Register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Create user in OU
        username = 'usertest'
        data, new_user = self.create_user(username)

        # 4 - Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Assign group to computer
        computer = db.nodes.find_one({'name': computer['name']})
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group)

        # 6 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])
        self.assertEqual(group['members'][1], user['_id'])

        # 7, 8 - Add policy in Group and check if this policy is applied in chef
        # node
        group_launcher_policy = self.get_default_user_policy()
        policy_path = group_launcher_policy['path'] + '.users.' + username + \
            '.launchers'
        group['policies'] = {text_type(group_launcher_policy['_id']): {
            'launchers': ['OUsLauncher']}}
        node_policy = self.add_and_get_policy(node=group,
            chef_node_id=chef_node_id, api_class=GroupResource,
            policy_path=policy_path)
        self.assertEqual(node_policy, ['OUsLauncher'])

        # 9 - Delete group
        self.delete_node(group, GroupResource)
        self.assertDeleted(field_name='name', field_value=new_group['name'])

        # 10 - Verification if the policy has been deleted from chef node
        node = NodeMock(chef_node_id, None)
        try:
            launchers = node.attributes.get_dotted(policy_path)
        except KeyError:
            launchers = None

        self.assertIsNone(launchers)

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_23_delete_group_in_domain_with_workstation_and_user(self,
        get_chef_api_method, get_cookbook_method, get_cookbook_method_tasks,
        NodeClass, ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method, TaskNodeClass, TaskClientClass):
        '''
        Test 23:
        1. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method,
            None, TaskNodeClass, TaskClientClass)
        self.cleanErrorJobs()

        # 1 - Create a group
        data, new_group = self.create_group('testgroup', ou_name='Domain 1')

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 2 - Register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Create user in OU
        username = 'usertest'
        data, new_user = self.create_user(username)

        # 4 - Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Assign group to computer
        computer = db.nodes.find_one({'name': computer['name']})
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group)

        # 6 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group)

        # 7 - Check if group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])
        self.assertEqual(group['members'][1], user['_id'])

        # 8 - Delete group
        request = self.dummy_get_request(group, GroupResource.schema_detail)
        group_api = GroupResource(request)
        group = group_api.get()
        self.delete_node(group, GroupResource)

        # 9 - Verification that the group has been delete from chef node, user
        # and workstation
        self.assertDeleted(field_name='name', field_value=new_group['name'])
        user = db.nodes.find_one({'name': username})
        group = db.nodes.find_one({'name': new_group['name']})
        workstation = db.nodes.find_one({'name': computer['name']})
        self.assertIsNone(group)
        self.assertEqual(workstation['memberof'], [])
        self.assertEqual(user['memberof'], [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_24_delete_OU_without_group_inside(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method, TaskNodeClass, TaskClientClass):
        '''
        Test 24:
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method,
            None, TaskNodeClass, TaskClientClass)
        self.cleanErrorJobs()

        # 1 - Create a group in domain
        data, new_group = self.create_group('test_group', ou_name='Domain 1')

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 2 - Register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Create user in OU
        username = 'usertest'
        data, new_user = self.create_user(username)

        # 4 - Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Assign group to computer
        computer = db.nodes.find_one({'name': computer['name']})
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group)

        # 6 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group)

        # 7 - Check if group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])
        self.assertEqual(group['members'][1], user['_id'])

        # 8 - Delete ou
        ou = db.nodes.find_one({'name': 'OU 1'})
        self.delete_node(ou, OrganisationalUnitResource)
        self.assertDeleted(field_name='name', field_value=ou['name'])

        # 10 - Verification if the user and computer have been disassociate from
        # group
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'], [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_25_priority_grouped_ous_workstation(self, get_chef_api_method, 
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method):
        '''
        Test 25:
        1. Check the policies pripority works using organisational unit
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method)
        self.cleanErrorJobs()

        # 1 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()
        policies = self.get_default_policies()

        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        for policy in policies:
            # 2 - Add policy in OU
            ou_1['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_1']}
            node_policy = self.add_and_get_policy(node=ou_1,
                chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
                policy_path=policies[policy]['path'])

            # 3 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertItemsEqual(node_policy, policies[policy][
                    'policy_data_node_1']['package_list'])
            else:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['shutdown_mode'])

            # 4 - Add policy in domain
            domain_1['policies'] = {text_type(policies[policy]['policy'][
                '_id']): policies[policy]['policy_data_node_2']}
            domain_policy = self.add_and_get_policy(node=domain_1,
                chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
                policy_path=policies[policy]['path'])

            if policies[policy]['policy']['is_mergeable']:
                # 5 - Verification if OU's and Domain's policy is applied in
                # chef node
                self.assertItemsEqual(domain_policy, [
                    {'name': 'gimp', 'version': 'latest', 'action': 'add'},
                    {'name': 'libreoffice', 'version': 'latest',
                     'action': 'add'}])
            else:
                # 5  Verification if OU's policy is applied in chef node
                self.assertEqual(domain_policy, policies[policy][
                    'policy_data_node_1']['shutdown_mode'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_26_priority_user_and_group(self, get_chef_api_method, 
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 26:
        1. Check the registration work station works
        2. Check the policies priority works using organisational unit and user
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 1 - Create user
        username = 'testuser'
        data, new_user = self.create_user(username)
        self.assertEqualObjects(data, new_user)

        # 2- Create a group
        data, new_group = self.create_group('testgroup')

        # 3 - Register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 4 - Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)

        # 5 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'],
            api_class=UserResource, group=new_group)

        policies = self.get_default_policies_user()
        group = db.nodes.find_one({'name': 'testgroup'})
        user = db.nodes.find_one({'name': username})
        for policy in policies:
            # 6 - Add policy in group
            group['policies'] = {text_type(policies[policy]['policy']['_id']):
                policies[policy]['policy_data_node_1']}
            name_element_policy = policies[policy]['policy_data_node_1']
            policy_path_1 = policies[policy]['path'] + username + '.' + \
                list(name_element_policy.keys())[0]
            node_policy = self.add_and_get_policy(node=group,
                chef_node_id=chef_node_id, api_class=GroupResource,
                policy_path=policy_path_1)
            # 7 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['desktops'])
            else:
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_1']['desktop_file'])
            # 8 - Add policy in user
            name_element_policy = policies[policy]['policy_data_node_2']
            policy_path_2 = policies[policy]['path'] + username + '.' + \
                list(name_element_policy.keys())[0]
            user['policies'] = {text_type(policies[policy]['policy']['_id']): 
                policies[policy]['policy_data_node_2']}
            node_policy = self.add_and_get_policy(node=user,
                chef_node_id=chef_node_id, api_class=UserResource,
                policy_path=policy_path_2)

            if policies[policy]['policy']['is_mergeable']:
                # 9 - Verification if this policy is applied in chef node
                self.assertItemsEqual(node_policy, [
                    {'name': 'sublime', 'action': 'add'},
                    {'name': 'kate', 'action': 'add'}])
                # 10 - Remove user's policy and verification if group's policy 
                # is applied in chef node
                policy_applied = self.remove_policy_and_get_dotted(user,
                    chef_node_id, UserResource, policy_path_1)
                self.assertItemsEqual(policy_applied, [
                    {'name': 'kate', 'action': 'add'}])
            else:
                # 9 - Verification if this policy is applied in chef node
                self.assertEqual(node_policy, policies[policy][
                    'policy_data_node_2']['desktop_file'])
                # 10 - Remove user's policy and verification if group's policy
                # is applied in chef node
                policy_applied = self.remove_policy_and_get_dotted(user,
                    chef_node_id, UserResource, policy_path_2)
                self.assertEqual(policy_applied, 'mountain.png')

        self.assertNoErrorJobs()


    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_28_repositories_are_mergeables(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 28:
        1. Check the repositories are mergeables
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create repository
        db = self.get_db()
        data, new_repo1 = self.create_repository('repository_1')

        # 2 - Create repository
        data, new_repo2 = self.create_repository('repository_2')

        # 3 - Register workstation in OU
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # Register admin
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        repository_policy = db.policies.find_one(
            {'slug': 'repository_can_view'})
        policy_path = repository_policy['path']

        # 4 - Add repository to workstation
        computer = db.nodes.find_one({'name': 'testing'})
        computer['policies'] = {text_type(repository_policy['_id']): 
                                {'object_related_list': [new_repo1['_id']]}}
        node_policy = self.add_and_get_policy(node=computer,
            chef_node_id=chef_node_id, api_class=ComputerResource,
            policy_path=policy_path)

        # 5 - Add repository 2 to OU
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        ou_1['policies'] = {text_type(repository_policy['_id']): {
            'object_related_list': [new_repo2['_id']]}}

        node_policy = self.add_and_get_policy(node=ou_1, 
            chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
            policy_path=policy_path)

        # 6 - Verification if the repositories are applied to user in chef node
        self.assertEmitterObjects(node_policy, [new_repo1, new_repo2], 
            fields=('name', 'uri'))

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_29_cert_policy(self, get_chef_api_method, get_cookbook_method,
        get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
        gettext, create_chef_admin_user_method, TaskNodeClass, TaskClientClass):
        '''
        Test 29:
        1. Check the policies priority works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method,
            None, TaskNodeClass, TaskClientClass)
        self.cleanErrorJobs()

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 1 - Create and register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 2 - Create user in OU
        username = 'usertest'
        data, new_user = self.create_user(username)

        # 3 - Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 4 - Add policy in OU
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        cert_res = db.policies.find_one({'slug': 'cert_res'})
        policy_dir = 'gecos_ws_mgmt.misc_mgmt.cert_res'
        ou_1['policies'] = {text_type(cert_res['_id']): {'java_keystores': 
            ["keystore_ou"], 'ca_root_certs': [{'name': "cert_ou",
                'uri': "uri_ou"}]}}
        node_policy = self.add_and_get_policy(node=ou_1,
            chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
            policy_path=policy_dir)

        # 5 - Verification if this policy is applied in chef node
        self.assertItemsEqual(node_policy.get('java_keystores'), ['keystore_ou'])
        self.assertItemsEqual(node_policy.get('ca_root_certs'), 
            [{u'name': u'cert_ou', u'uri': u'uri_ou'}])

        # 6 - Add policy in workstation
        computer = db.nodes.find_one({'name': 'testing'})
        computer['policies'] = {text_type(cert_res['_id']): {'java_keystores':
            ["keystore_ws"], 'ca_root_certs': [{'name': "cert_ws",
                'uri': "uri_ws"}]}}
        node_policy = self.add_and_get_policy(node=computer,
            chef_node_id=chef_node_id, api_class=ComputerResource,
            policy_path=policy_dir)

        # 7 - Verification if this policy is applied in chef node
        self.assertItemsEqual(node_policy.get('java_keystores'), ['keystore_ou',
            'keystore_ws'])
        self.assertItemsEqual(node_policy.get('ca_root_certs'), [
            {u'name': u'cert_ou', u'uri': u'uri_ou'},
            {u'name': u'cert_ws', u'uri': u'uri_ws'}])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_30_recalc_command_cert_policy(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method, TaskNodeClass, TaskClientClass):

        if DISABLE_TESTS: return

        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext, create_chef_admin_user_method,
            None, TaskNodeClass, TaskClientClass)
        self.cleanErrorJobs()

        # 1 - 7
        self.test_29_cert_policy()

        node = NodeMock(CHEF_NODE_ID, None)

        # 8 - Modify the data in chef node
        policy_path = 'gecos_ws_mgmt.misc_mgmt.cert_res.ca_root_certs'
        node.attributes.set_dotted(policy_path, [
            {u'name': u'cert_ou_fake', u'uri': u'uri_ou'},
            {u'name': u'cert_ws', u'uri': u'uri_ws_fake'}])
        node.save()

        # 9 - Check if the data has beed modified in chef node
        node_policy = node.attributes.get_dotted(policy_path)
        self.assertEqual(node_policy, [
            {u'name': u'cert_ou_fake', u'uri': u'uri_ou'}, 
            {u'name': u'cert_ws', u'uri': u'uri_ws_fake'}])

        # 10 - Runs recalc command
        self.recalc_policies()

        # 11 - Check if the data applied in chef node is correct
        node_policy = node.attributes.get_dotted(policy_path)
        self.assertEqual(node_policy, [
            {u'name': u'cert_ou', u'uri': u'uri_ou'},
            {u'name': u'cert_ws', u'uri': u'uri_ws'}])

        self.assertNoErrorJobs()


    @mock.patch('gecoscc.api.computers._')
    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_31_help_channel(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method, TaskNodeClass, TaskClientClass,
        gettext_computers):

        '''
        31. Test the help channel functionality
        '''

        if DISABLE_TESTS: return

        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext, create_chef_admin_user_method,
            None, TaskNodeClass, TaskClientClass)
        gettext_computers.side_effect = gettext_mock
        self.cleanErrorJobs()

        db = self.get_db()
        db.helpchannel.delete_many({})
        

        # 1 - Register workstation in OU
        chef_node_id = CHEF_NODE_ID
        self.register_computer()
        
        # 2-  Register admin
        admin_username = 'superuser'
        self.add_admin_user(admin_username)
        
        # 3 - Create and register user in chef node
        username = 'usertest'
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)
        
        
        # 4 - Create request upload the log files
        secret = self.registry.settings['helpchannel.known_message']
        # (cipher the secret message with the public key)
        with open('gecoscc/test_resources/client.pem') as client_f:
            client_pem = client_f.read()
            private_key = RSA.importKey(client_pem)
            secret = private_key.decrypt((secret.encode(),))       
            
        data = {
            'node_id': CHEF_NODE_ID,
            'username':  username,
            'secret': secret.hex(),
            'gcc_username': 'test',
            'hc_server': '127.0.0.1'
            
        }
        request_post = self.get_dummy_json_post_request(data)
        request_post.POST = data
        node_api = HelpChannelClientLogin(request_post)
        response = node_api.post()
        
        # 5 - Check if the response is valid
        self.assertEqual(response['ok'], True, str(response))
        
        # 6 - Check helpchannel data
        hcdata = db.helpchannel.find_one(
            {'computer_node_id': CHEF_NODE_ID})
        self.assertEqual(response['token'], hcdata['token'])
        token = response['token']
        print('Token: %s'%(token))

        # 7 - Test fetch operation
        data = {
            'connection_code': token 
        }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/help-channel-client/fetch'
        request.GET = data
        node_api = HelpChannelClientFetch(request)
        response = node_api.get()
        
        self.assertEqual(response['ok'], True, str(response))


        # 8 - Accept the support
        data = {
            'connection_code': token 
        }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/help-channel-client/accept'
        request.GET = data
        node_api = HelpChannelClientAccept(request)
        response = node_api.get()
        
        self.assertEqual(response['ok'], True, str(response))

        # 9 - Check the token        
        data = {
            'connection_code': token
        }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/help-channel-client/check'
        request.GET = data
        request.remote_addr = '127.0.0.1'
        
        node_api = HelpChannelClientCheck(request)
        response = node_api.get()
        
        self.assertEqual(response['ok'], True, str(response))


        # 10 - Check help channel data in computer
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer,
            ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()
        self.assertEqual(computer['helpchannel']['current']['action'],
                         'accepted')
        
        
        # 11 - Give support to the user
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer,
            ComputerSupportResource.schema_detail)
        computer_api = ComputerSupportResource(request)
        try:
            computer = computer_api.get()
        except HTTPFound as ex:
            self.assertEqual(ex.location, '127.0.0.1?repeaterID=ID:%s'%(token))
            
        # 12 - Finish the support
        data = {
            'connection_code': token,
            'finisher': 'user'
        }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/help-channel-client/finish'
        request.GET = data
        request.remote_addr = '127.0.0.1'
        
        node_api = HelpChannelClientFinish(request)
        response = node_api.get()
        
        self.assertEqual(response['ok'], True, str(response))
        
        
        self.assertNoErrorJobs()


    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_32_refresh_policies(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method, TaskNodeClass, TaskClientClass):

        if DISABLE_TESTS: return

        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext, create_chef_admin_user_method,
            None, TaskNodeClass, TaskClientClass)
        self.cleanErrorJobs()

        # 1 - 7
        self.test_29_cert_policy()

        node = NodeMock(CHEF_NODE_ID, None)

        # 8 - Modify the data in chef node
        policy_path = 'gecos_ws_mgmt.misc_mgmt.cert_res.ca_root_certs'
        node.attributes.set_dotted(policy_path, [
            {u'name': u'cert_ou_fake', u'uri': u'uri_ou'},
            {u'name': u'cert_ws', u'uri': u'uri_ws_fake'}])
        node.save()

        # 9 - Check if the data has beed modified in chef node
        node_policy = node.attributes.get_dotted(policy_path)
        self.assertEqual(node_policy, [
            {u'name': u'cert_ou_fake', u'uri': u'uri_ou'}, 
            {u'name': u'cert_ws', u'uri': u'uri_ws_fake'}])

        # 10 - Refresh policies
        computer = self.get_db().nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer,
            ComputerResource.schema_detail)
        node_api = ComputerResource(request)
        computer = node_api.get()


        request_put = self.get_dummy_json_put_request(computer,
            path='/api/computers/')
        request_put.matchdict['oid'] = computer['_id']
        request_put.POST = computer
        request_put.GET = { 'action': 'refresh_policies'}
        request_put.validated = computer
        node_api = ComputerResource(request_put)
        response = node_api.put()
        
        self.assertEqual(response['name'], 'testing')
        
        # 11 - Check if the data applied in chef node is correct
        node = NodeMock(CHEF_NODE_ID, None)
        node_policy = node.attributes.get_dotted(policy_path)
        self.assertEqual(node_policy, [
            {u'name': u'cert_ou', u'uri': u'uri_ou'},
            {u'name': u'cert_ws', u'uri': u'uri_ws'}])

        self.assertNoErrorJobs()


    def test_33_mongo_dump_restore(self):

        '''
        33. Test the mongo dump and restore capabilities
        '''

        if DISABLE_TESTS: return

        self.cleanErrorJobs()

        db = self.registry.settings['mongodb']

        # 1 - Create a backup
        db.dump('/tmp/test_dump')
        
        # 2 - Remove the data and check that is empty
        self.drop_database()
        
        ou1 = db.get_database().nodes.find_one({'name': 'OU 1'})
        self.assertTrue(ou1 is None)
        
        
        # 3 - Restore the database and check that the data is back
        db.restore('/tmp/test_dump')
       
        ou1 = db.get_database().nodes.find_one({'name': 'OU 1'})
        self.assertFalse(ou1 is None)

        
        



class MovementsTests(BaseGecosTestCase):

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_01_printers_movements(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 01:
        1. Check the printers movements work
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create printer
        data, new_printer = self.create_printer('Testprinter')

        # 2 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Add printer to workstation and check if it is applied in chef node
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer,
            ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()

        printer_policy = db.policies.find_one({'slug': 'printer_can_view'})
        computer['policies'] = {text_type(printer_policy['_id']): {
            'object_related_list': [new_printer['_id']]}}
        policy_path = printer_policy['path']
        self.add_and_get_policy(node=computer, chef_node_id=chef_node_id,
            api_class=ComputerResource, policy_path=policy_path)

        printer = db.nodes.find_one({'name': 'Testprinter'})
        # 4 - Move printer to the OU path
        try:
            printer_update = self.update_node(obj=new_printer,
                field_name='path', field_value=ou_1['path'],
                api_class=PrinterResource, is_superuser=False)
        except HTTPForbidden:
            printer_update = printer

        # 5 - Checks if the printer has been moved and check if the policy has
        # been updated
        self.assertEqual(printer_update['path'], printer['path'])
        node = NodeMock(CHEF_NODE_ID, None)
        printer_policy = node.attributes.get_dotted(policy_path)
        self.assertEqualObjects(printer_policy[0], new_printer,
            fields=('oppolicy', 'model', 'uri', 'name', 'manufacturer'))
        # 6 - Move printer to the OU path like superadmin
        printer_update = self.update_node(obj=new_printer, field_name='path',
            field_value=ou_1['path'], api_class=PrinterResource,
            is_superuser=True)

        # 7 - Checks if the printer has been moved
        self.assertNotEqual(printer_update['path'], printer['path'])

        # 8 - Create another OU
        data, ou_2 = self.create_ou('OU 2')

        # 9 - Move printer to OU 2 like superadmin
        printer_update = self.update_node(obj=new_printer, field_name='path',
            field_value=ou_2['path'] + ',' + text_type(ou_2['_id']),
            api_class=PrinterResource, is_superuser=True)

        # 10 - Check if the printer is moved and the policy has been updated
        self.assertNotEqual(printer_update['path'], printer['path'])
        node = NodeMock(CHEF_NODE_ID, None)
        printer_policy = node.attributes.get_dotted(policy_path)
        self.assertEqual(printer_policy, [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_02_shared_folder_movements(self, get_chef_api_method, 
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 02:
        1. Check the shared folder movements work
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # Register admin
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 1 - Create storage
        db = self.get_db()
        data, new_storage = self.create_storage('shared folder')

        # 2 - Create OU 2
        data, ou_2 = self.create_ou('OU 2')
        # 3 - Create ws and user
        username = 'testuser'
        data, new_user = self.create_user(username)
        self.assertEqualObjects(data, new_user)

        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 4 - Register user in ws
        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)

        # 5 - Add storage to user and check if it is applied in chef node
        user = db.nodes.find_one({'name': username})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        storage_policy = db.policies.find_one({'slug': 'storage_can_view'})

        user['policies'] = {text_type(storage_policy['_id']): {
            'object_related_list': [new_storage['_id']]}}
        policy_path = storage_policy['path'] + '.' + username + '.gtkbookmarks'
        self.add_and_get_policy(node=user, chef_node_id=chef_node_id,
                                api_class=UserResource, policy_path=policy_path)

        storage = db.nodes.find_one({'name': 'shared folder'})
        # 6 - Move storage
        try:
            storage_update = self.update_node(obj=new_storage,
                field_name='path', field_value=ou_2['path'],
                api_class=StorageResource, is_superuser=False)
        except HTTPForbidden:
            storage_update = storage

        # 7- Check if the storage has been moved
        self.assertEqual(storage_update['path'], storage['path'])

        # 8 - Move storage to the OU path like admin
        storage_update = self.update_node(obj=new_storage, field_name='path',
            field_value=ou_2['path'], api_class=StorageResource,
            is_superuser=True)
        # 9 - Check if the storage is moved and the policy has been updated
        self.assertNotEqual(storage_update['path'], storage['path'])
        node = NodeMock(CHEF_NODE_ID, None)
        printer_policy = node.attributes.get_dotted(policy_path)
        self.assertEqualObjects(printer_policy[0], storage,
            fields=('oppolicy', 'model', 'uri', 'name', 'manufacturer'))
        # 10 - Create another OU
        data, ou_3 = self.create_ou('OU 3')

        # 11 - Move storage in the OU 3 like admin
        storage_update = self.update_node(obj=new_storage, field_name='path',
            field_value=ou_3['path'] + ',' + ou_3['_id'],
            api_class=StorageResource, is_superuser=True)

        # 12 - Check if the storage is moved and the policy has been updated
        self.assertNotEqual(storage_update['path'], storage['path'])
        node = NodeMock(CHEF_NODE_ID, None)
        try:
            printer_policy = node.attributes.get_dotted(policy_path)
            self.assertEqual(printer_policy, [])
        except KeyError:
            self.assertEqual([], [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_03_repository_movements(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 03:
        1. Check the repository movements work
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create printer
        data, new_repository = self.create_repository('Testrepo')

        # 2 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Add repository to workstation
        repository_policy = db.policies.find_one(
            {'slug': 'repository_can_view'})
        policy_path = repository_policy['path']
        computer = db.nodes.find_one({'name': 'testing'})
        computer['policies'] = {text_type(repository_policy['_id']): {
            'object_related_list': [new_repository['_id']]}}
        self.add_and_get_policy(node=computer, chef_node_id=chef_node_id,
            api_class=ComputerResource, policy_path=policy_path)

        repository = db.nodes.find_one({'name': 'Testrepo'})
        # 4 - Move repository to the OU path
        try:
            repository_update = self.update_node(obj=new_repository,
                field_name='path', field_value=ou_1['path'],
                api_class=RepositoryResource, is_superuser=False)
        except HTTPForbidden:
            repository_update = repository
        # 5 - Checks if the repository has been moved
        self.assertEqual(repository_update['path'], repository['path'])

        # 6 - Move repository to the OU path like admin
        repository_update = self.update_node(obj=new_repository,
            field_name='path', field_value=ou_1['path'],
            api_class=RepositoryResource, is_superuser=True)

        # 7 - Checks if the repository has been moved
        self.assertNotEqual(repository_update['path'], repository['path'])

        # 8 - Create another OU
        data, ou_2 = self.create_ou('OU 2')

        # 9 - Move printer to OU 2 like superadmin
        repository = db.nodes.find_one({'name': 'Testrepo'})
        repository_path = repository['path']
        repository_update = self.update_node(obj=repository, field_name='path',
            field_value=ou_2['path'] + ',' + text_type(ou_2['_id']),
            api_class=RepositoryResource,
            is_superuser=True)

        # 10 - Check if the printer is moved and the policy has been updated
        self.assertNotEqual(repository_update['path'], repository_path)
        node = NodeMock(CHEF_NODE_ID, None)
        printer_policy = node.attributes.get_dotted(policy_path)
        self.assertEqual(printer_policy, [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_04_groups_movements(self, get_chef_api_method, get_cookbook_method,
        get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
        gettext, create_chef_admin_user_method):
        '''
        Test 04:
        1. Check the groups movements work
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1- Create a group
        data, new_group = self.create_group('testgroup')

        # 2 - Register a workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        self.register_computer()
        computer = db.nodes.find_one({'name': 'testing'})

        # 3 - Assign group to computer
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': 'testgroup'})
        self.assertEqual(group['members'][0], computer['_id'])

        # 4 - move group to the OU path
        try:
            self.update_node(obj=group, field_name='path',
                field_value=ou_1['path'], api_class=GroupResource,
                is_superuser=False)
            group_update = db.nodes.find_one({'name': 'testgroup'})
            
        except HTTPForbidden:
            group_update = group

        # 5 - Check if the groups has been moved
        self.assertEqual(group_update['path'], group['path'])

        # 6 - move group to the OU path like admin
        group = db.nodes.find_one({'name': 'testgroup'})
        group_path = group['path']
        self.update_node(obj=group, field_name='path',
            field_value=ou_1['path'], api_class=GroupResource,
            is_superuser=True)
        group_update = db.nodes.find_one({'name': 'testgroup'})
        # 7 - Check if the groups has been moved
        self.assertNotEqual(group_update['path'], group_path)
        self.assertNotEqual(group_update['members'], [])

        # 8 - Create another OU
        data, ou_2 = self.create_ou('OU 2')

        # 9 - Move group to OU 2 like superadmin
        group = db.nodes.find_one({'name': 'testgroup'})
        group_path = group['path']
        self.update_node(obj=group, field_name='path',
            field_value=ou_2['path'] + ',' + text_type(ou_2['_id']),
            api_class=GroupResource,
            is_superuser=True)
        group_update = db.nodes.find_one({'name': 'testgroup'})

        # 10 - Check if the group is moved and the policy has been updated
        self.assertNotEqual(group_update['path'], group_path)
        self.assertEqual(group_update['members'], [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_05_groups_movements_domain(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 05:
        1. Check the groups movements work
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1- Create a group
        data, new_group = self.create_group('testgroup')

        # 2 - Register a workstation
        db = self.get_db()
        self.register_computer()
        computer = db.nodes.find_one({'name': 'testing'})

        # 3 - Assign group to computer
        self.assign_group_to_node(node_name=computer['name'],
            api_class=ComputerResource, group=new_group)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': 'testgroup'})
        self.assertEqual(group['members'][0], computer['_id'])

        # 4 - Create domain
        data = {'name': 'Flag',
                'type': 'ou',
                'path': 'root',
                'source': 'gecos'}

        request_post = self.get_dummy_json_post_request(data,
            OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request_post)
        flag_new = ou_api.collection_post()

        data, domain = self.create_domain('Domain 2', flag_new)

        # 5 - move group to the OU path like admin
        try:
            group_update = self.update_node(obj=new_group, field_name='path',
                field_value=domain['path'], api_class=GroupResource,
                is_superuser=True)
        except KeyError:
            group_update = group

        # 6 - Check if the groups has been moved
        self.assertEqual(group_update['path'], group['path'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_06_OUs_movements(self, get_chef_api_method, get_cookbook_method,
        get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
        gettext, create_chef_admin_user_method):
        '''
        Test 06:
        1. Check the ous movements work
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1- Create OU 2
        data, new_ou = self.create_ou('OU 2', 'OU 1')

        # 2 - Register a workstation
        db = self.get_db()
        self.register_computer(ou_name=new_ou['name'])

        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        ou_2 = db.nodes.find_one({'name': 'OU 2'})
        # 3 - Move OU 2 to OU 1 path
        try:
            ou_moved = self.update_node(obj=new_ou, field_name='path',
                field_value=ou_1['path'], api_class=OrganisationalUnitResource,
                is_superuser=False)

        except HTTPForbidden:
            ou_moved = ou_2

        # 7- Check if the storage has been moved
        self.assertEqual(ou_moved['path'], ou_2['path'])

        # 8 - Move printer to the OU path like admin
        ou_moved = self.update_node(obj=new_ou, field_name='path',
            field_value=ou_1['path'], api_class=OrganisationalUnitResource,
            is_superuser=True)

        # 9- Check if the storage has been moved
        self.assertNotEqual(ou_moved['path'], ou_2['path'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_07_OUs_movements_domain(self, get_chef_api_method,
        get_cookbook_method, get_cookbook_method_tasks, NodeClass,
        ChefNodeClass, isinstance_method, gettext,
        create_chef_admin_user_method):
        '''
        Test 07:
        1. Check the ous movements work
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()

        # 1 - Create domain
        data = {'name': 'Flag',
                'type': 'ou',
                'path': 'root',
                'source': 'gecos'}

        request_post = self.get_dummy_json_post_request(data,
            OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request_post)
        flag_new = ou_api.collection_post()

        data, domain = self.create_domain('Domain 2', flag_new)

        # 2 - Register a workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        self.register_computer(ou_name=ou_1['name'])

        # 3 - Move OU 1 to Domain path like admin
        try:
            ou_moved = self.update_node(obj=ou_1, field_name='path',
                field_value=domain['path'],
                api_class=OrganisationalUnitResource,
                is_superuser=True)
        except HTTPForbidden:
            ou_moved = ou_1

        # 9- Check if the storage has been moved
        self.assertEqual(ou_moved['path'], ou_1['path'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_08_complete_policy(self, get_chef_api_method, get_cookbook_method,
        get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
        gettext, create_chef_admin_user_method):
        '''
        Test 08:
        1. Check the ous movements work
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, gettext_mock, create_chef_admin_user_method)
        self.cleanErrorJobs()
        chef_node_id = CHEF_NODE_ID

        # 1 - Get OU 1 (it belongs to the basic structure)
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})

        # 2 - Create OU 2
        data, ou_2 = self.create_ou('OU 2')

        # 3 - Create OU 3
        data, ou_3 = self.create_ou('OU 3', 'OU 1')

        # 4 - Create user, workstation, storage and 5 - Assign user to computer
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        username = 'testuser'
        data, user = self.create_user(username, 'OU 3')
        self.assertEqualObjects(data, user)

        chef_node_id = CHEF_NODE_ID
        self.register_computer(ou_name=ou_3['name'])

        self.assign_user_to_node(gcc_superusername=admin_username,
            chef_node_id=chef_node_id, username=username)

        data, storage = self.create_storage('shared folder', ou_3['name'])
        data, storage_ou_1 = self.create_storage('shared folder_ou_1',
                                                 ou_1['name'])

        user = db.nodes.find_one({'name': username})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        storage_policy = db.policies.find_one({'slug': 'storage_can_view'})

        user['policies'] = {text_type(storage_policy['_id']): {
            'object_related_list': [storage['_id']]}}
        storage_policy_path = storage_policy['path'] + '.' + username + \
            '.gtkbookmarks'
        node_policy = self.add_and_get_policy(node=user,
            chef_node_id=chef_node_id, api_class=UserResource,
            policy_path=storage_policy_path)

        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        ou_1['policies'] = {text_type(storage_policy['_id']): {
            'object_related_list': [storage_ou_1['_id']]}}
        node_policy = self.add_and_get_policy(node=ou_1,
            chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
            policy_path=storage_policy_path)

        # 7 - add package policy to OU_1, OU_3 and ws
        package_res_policy = self.get_default_ws_policy()
        policy_path = package_res_policy['path'] + '.package_list'
        ou_1['policies'] = {text_type(package_res_policy['_id']): {
            'package_list': [
                {'name': 'gimp', 'version': 'latest', 'action': 'add'}]}}
        package_res_node_policy = self.add_and_get_policy(node=ou_1,
            chef_node_id=chef_node_id, api_class=OrganisationalUnitResource,
            policy_path=policy_path)

        apply_package = [
            {'node': 'testing', 'api_type': ComputerResource,
             'package': 'sublime'},
            {'node': 'OU 1', 'api_type': OrganisationalUnitResource,
             'package': 'gimp'},
            {'node': 'OU 3', 'api_type': OrganisationalUnitResource,
             'package': 'kate'}]

        package_res_policy = self.get_default_ws_policy()
        policy_path = package_res_policy['path'] + '.package_list'

        for node in apply_package:
            node_to_apply = db.nodes.find_one({'name': node['node']})
            node_to_apply['policies'] = {text_type(package_res_policy['_id']): {
                'package_list': [
                    {'name': node['package'], 'version': 'latest',
                     'action': 'add'}]}}
            package_res_node_policy = self.add_and_get_policy(
                node=node_to_apply, chef_node_id=chef_node_id,
                api_class=node['api_type'], policy_path=policy_path)

        self.assertItemsEqual(package_res_node_policy, [
            {'name': 'kate', 'version': 'latest', 'action': 'add'},
            {'name': 'sublime', 'version': 'latest', 'action': 'add'},
            {'name': 'gimp', 'version': 'latest', 'action': 'add'}])
        self.assertEmitterObjects(node_policy, [storage_ou_1, storage],
            fields=('name', 'uri'))

        # 8 - Move OU 3 to OU 1 path
        ou_3 = db.nodes.find_one({'name': 'OU 3'})
        self.update_node(obj=ou_3, field_name='path',
            field_value=ou_1['path'], api_class=OrganisationalUnitResource,
            is_superuser=True)

        # 9 - Check if the policies has been updated in chef node
        node = NodeMock(chef_node_id, None)
        node_storage_policy = node.attributes.get_dotted(storage_policy_path)
        node_package_policy = node.attributes.get_dotted(policy_path)

        self.assertEmitterObjects(node_storage_policy, [storage],
            fields=('name', 'uri'))
        self.assertItemsEqual(node_package_policy, [
            {'name': 'kate', 'version': 'latest', 'action': 'add'},
            {'name': 'sublime', 'version': 'latest', 'action': 'add'}])

        self.assertNoErrorJobs()



class SuperadminTests(BaseGecosTestCase):

    def _parse_settings(self, settings):
        parsed = {}
        for elm in settings:
            parsed[elm['key']] = elm['value']
            
        return parsed


    @mock.patch('gecoscc.views.settings._')
    def test_01_settings(self, gettext):
        '''
        Test 1: Check that the settings view works
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(gettext=gettext)
        db = self.get_db()
        db.settings.drop()

        
        # 1 - Create request access to settings view's
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = settings(context, request)
        parsed = self._parse_settings(response['settings'])
        
        # 2 - Check if the response is valid
        self.assertEqual(parsed['firstboot_api.version'],
                         self.registry.settings['firstboot_api.version'])
        
        
        # 3 - Modify a setting
        data = '{"firstboot_api___comments":"None",' \
            '"firstboot_api___organization_name":"Junta de Andalucía",'\
            '"firstboot_api___version":"0.2.0_test",'\
            '"update_error_interval":24,'\
            '"printers___urls":['\
              '"http://www.openprinting.org/download/foomatic/'\
                'foomatic-db-nonfree-current.tar.gz",'\
               '"http://www.openprinting.org/download/foomatic/'\
                'foomatic-db-current.tar.gz"],'\
            '"repositories":['\
                '"http://v2.gecos.guadalinex.org/gecos/",'\
                '"http://v2.gecos.guadalinex.org/ubuntu/",'\
                '"http://v2.gecos.guadalinex.org/mint/",'\
                '"http://v3.gecos.guadalinex.org/gecos/",'\
                '"http://v3.gecos.guadalinex.org/ubuntu/",'\
                '"http://v3.gecos.guadalinex.org/mint/"],'\
            '"mimetypes":["image/jpeg","image/png"]}'
        request = self.get_dummy_request()
        request.POST = { 'data': data }
        context = LoggedFactory(request)
        response = settings_save(context, request)
        self.assertEqual(response.status_code, 200)
        
        # 4 - Check that the setting has changed
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = settings(context, request)
        parsed = self._parse_settings(response['settings'])
        
        self.assertEqual(parsed['firstboot_api.version'],
                         '0.2.0_test')
        
        # 4 - Check mime-types
        data = { }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/mimetypes/'
        request.GET = data
        node_api = MimestypesResource(request)
        response = node_api.collection_get()
        
        self.assertEqual(response['settings'][0]['value'],
                         '["image/jpeg", "image/png"]')
        
        
        # 5 -Change the mime-types
        data = '{"firstboot_api___comments":"None",' \
            '"firstboot_api___organization_name":"Junta de Andalucía",'\
            '"firstboot_api___version":"0.2.0_test",'\
            '"update_error_interval":24,'\
            '"printers___urls":['\
              '"http://www.openprinting.org/download/foomatic/'\
                'foomatic-db-nonfree-current.tar.gz",'\
               '"http://www.openprinting.org/download/foomatic/'\
                'foomatic-db-current.tar.gz"],'\
            '"repositories":['\
                '"http://v2.gecos.guadalinex.org/gecos/",'\
                '"http://v2.gecos.guadalinex.org/ubuntu/",'\
                '"http://v2.gecos.guadalinex.org/mint/",'\
                '"http://v3.gecos.guadalinex.org/gecos/",'\
                '"http://v3.gecos.guadalinex.org/ubuntu/",'\
                '"http://v3.gecos.guadalinex.org/mint/"],'\
            '"mimetypes":["image/jpeg","image/png","text/html"]}'
        request = self.get_dummy_request()
        request.POST = { 'data': data }
        context = LoggedFactory(request)
        response = settings_save(context, request)
        self.assertEqual(response.status_code, 200)
        
        
        # 6 - Check mime-types
        data = { }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/mimetypes/'
        request.GET = data
        node_api = MimestypesResource(request)
        response = node_api.collection_get()
        
        self.assertEqual(response['settings'][0]['value'],
                         '["image/jpeg", "image/png", "text/html"]')
        

    @mock.patch('gecoscc.models.get_chef_api')    
    @mock.patch('gecoscc.utils._get_chef_api')    
    @mock.patch('gecoscc.views.admins._')
    @mock.patch('gecoscc.models.gettext')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.i18n.gettext')
    @mock.patch('gecoscc.views.admins.UpdateModel')
    def test_02_updates(self, update_model, gettext, gettext_forms, gettext_models,
                        gettext_i18n, get_chef_api_method,
                        get_chef_api_models_method):
        '''
        Test 2: Check that the updates view works
        '''
        if DISABLE_TESTS: return

        update_model.side_effect = UpdateModelMock        
        gettext.side_effect = gettext_mock
        gettext_forms.side_effect = gettext_mock
        gettext_models.side_effect = gettext_mock
        gettext_i18n.side_effect = gettext_mock
        get_chef_api_method.side_effect = _get_chef_api_mock
        get_chef_api_models_method.side_effect = get_chef_api_mock
        
        db = self.get_db()
        db.updates.drop()
        if os.path.isdir('/tmp/updates/'):
            shutil.rmtree('/tmp/updates/')

        # 1 - Create request access to updates view's
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = updates(context, request)

        # Check the response (there is no updates yet)
        self.assertEqual(response['latest'], '-001')


        # 2 - Check the view to add a new update
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = updates_add(context, request)
        self.assertTrue(response['update_form'].startswith('<form'))


        # 3 - Create a new update
        fp = open('gecoscc/test_resources/update-test.zip')
        headers = {
            'content-type': 'application/zip',
            'content-disposition': 'form-data; name="upload"; '\
                'filename="update-test.zip"'
        }
        environ = {
            'REQUEST_METHOD': 'POST'
        }
        data = {
            '_charset_': 'UTF-8',
            '__formid__': 'deform',
            '_submit': '_submit',
            'remote_file': '',
            '__start__': 'local_file:mapping',
            'upload': FieldStorage(fp, headers, environ=environ),  
            '__end__': 'local_file:mapping',
        }
        
        request = self.get_dummy_request()
        request.POST = data
        pyramid.threadlocal.get_current_request().VERSION = GCCUI_VERSION

        context = LoggedFactory(request)
        response = updates_add(context, request)
        fp.close()
        self.assertTrue(isinstance(response, HTTPFound))
         
         
        # 4 - Check that the update was created
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = updates(context, request)

        # Check the response (there is no updates yet)
        self.assertEqual(list(response['updates'])[0]['name'], 'update-test.zip')
         

        # 5 - Get the update information
        data = {}
        matchdict = { 'oid': 'test' }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/updates/'
        request.GET = data
        request.matchdict = matchdict
        update_api = UpdateResource(request)
        response = update_api.get()
 
        self.assertEqual(response['_id'], 'test')
        
        # 6 - Launch the update tail thread
        data = { 'tail': True }
        matchdict = { 'oid': 'test' }
        request = self.get_dummy_request()
        request.method = 'GET'
        request.errors = Errors()
        request.path = '/api/updates/'
        request.GET = data
        request.matchdict = matchdict
        update_api = UpdateResource(request)
        response = update_api.get()
 
        self.assertEqual(response, None)
        
        # Wait and see the console for errors
        time.sleep(1)
        
        # 7 - Check the update log
        request = self.get_dummy_request()
        matchdict = { 'sequence': 'test', 'rollback': '' }
        request.path = '/updates/log/test/'
        request.matchdict = matchdict
        context = LoggedFactory(request)
        response = updates_log(context, request)

        # Check the response
        self.assertTrue('This is just a test' in response.body.decode('utf-8'))
        
        
        # 8 - Download the update file
        request = self.get_dummy_request()
        matchdict = { 'id': 'test' }
        request.path = '/updates/download/test/'
        request.matchdict = matchdict
        context = LoggedFactory(request)
        response = updates_download(context, request)

        # Check that the response is a ZIP file
        self.assertEqual(response.body[0:2].decode('UTF-8'), 'PK')
        
        # 9- Repeat the update
        request = self.get_dummy_request()
        matchdict = { 'sequence': 'test' }
        request.path = '/updates/repeat/test/'
        request.matchdict = matchdict
        context = LoggedFactory(request)
        response = updates_repeat(context, request)

        # Check the response
        self.assertTrue(isinstance(response, HTTPFound))

        
        # 10 - Launch the operation to get the rollback log while being
        # generated
        matchdict = { 'sequence': 'test', 'rollback': 'rollback' }
        request.path = '/updates/tail/test/'
        request.matchdict = matchdict
        context = LoggedFactory(request)
        response = updates_tail(context, request)

        # Check the response
        self.assertEqual(response['rollback'], 'rollback')
        


    @mock.patch('gecoscc.models.get_chef_api')    
    @mock.patch('gecoscc.utils._get_chef_api')    
    @mock.patch('gecoscc.views.admins._')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.models.gettext')
    @mock.patch('gecoscc.i18n.gettext')
    @mock.patch('gecoscc.views.admins.AdminUser')
    @mock.patch('gecoscc.views.admins.Permissions')    
    @mock.patch('gecoscc.views.admins.AdminUserVariables')
    def test_03_admins(self, adminuservariablesmodel,
                       permissionsmodel, adminusermodel, gettext,
                       gettext_forms, gettext_models, gettext_i18n,
                       get_chef_api_method, get_chef_api_models_method):
        '''
        Test 3: Check that the administrator users views works
        '''
        if DISABLE_TESTS: return
        
        adminuservariablesmodel.side_effect = AdminUserVariablesMock
        permissionsmodel.side_effect = PermissionsMock
        adminusermodel.side_effect = AdminUserMock
        gettext.side_effect = gettext_mock
        gettext_forms.side_effect = gettext_mock
        gettext_models.side_effect = gettext_mock
        gettext_i18n.side_effect = gettext_mock
        get_chef_api_method.side_effect = _get_chef_api_mock
        get_chef_api_models_method.side_effect = get_chef_api_mock
        
        db = self.get_db()

        # 1 - Create request access to updates view's
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = admins(context, request)

        # Check the response
        admin_users = list(response['admin_users'])
        self.assertEqual(len(admin_users), 1)
        self.assertEqual(admin_users[0]['username'], 'test')

        
        # 2 - Check the view to add a new user
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = admin_add(context, request)
        self.assertTrue(response['admin_user_form'].startswith('<form'))

        # 3 - Create a new user
        data = {
            '_charset_': 'UTF-8',
            '__formid__': 'deform',
            '_submit': '_submit',
            'email': 'new@user.com',
            'password': 'newuser',
            'repeat_password': 'newuser',
            'first_name': 'New',
            'last_name': 'User',
            'username': 'newuser'
        }
        
        request = self.get_dummy_request()
        request.POST = data
        context = LoggedFactory(request)
        response = admin_add(context, request)
        self.assertTrue(isinstance(response, HTTPFound))

        # Check the user list
        request = self.get_dummy_request()
        request.GET = { 'q': 'newuser' }
        context = LoggedFactory(request)
        response = admins(context, request)
        admin_users = list(response['admin_users'])
        self.assertEqual(len(admin_users), 1)
        self.assertEqual(admin_users[0]['username'], 'newuser')
        

        # 4 - Check the view to edit a new user
        request = self.get_dummy_request()
        request.matchdict = { 'username': 'newuser' }
        context = LoggedFactory(request)
        response = admin_edit(context, request)
        self.assertTrue(response['admin_user_form'].startswith('<form'))

        # 5 - Edit user
        data = {
            '_charset_': 'UTF-8',
            '__formid__': 'deform',
            '_submit': '_submit',
            'email': 'new@user.com',
            'password': 'newuser',
            'repeat_password': 'newuser',
            'first_name': 'New New',
            'last_name': 'User'
        }
        
        request = self.get_dummy_request()
        request.POST = data
        request.matchdict = { 'username': 'newuser' }
        context = LoggedFactory(request)
        response = admin_edit(context, request)
        
        self.assertTrue(response['admin_user_form'].startswith('<form'))

        # Check the user list
        request = self.get_dummy_request()
        request.GET = { 'q': 'newuser' }
        context = LoggedFactory(request)
        response = admins(context, request)
        admin_users = list(response['admin_users'])
        self.assertEqual(len(admin_users), 1)
        self.assertEqual(admin_users[0]['first_name'], 'New New')

        

        # 6 - Check the view to change the OUs that the administrator
        # user can manage
        request = self.get_dummy_request()
        request.matchdict = { 'username': 'newuser' }
        context = LoggedFactory(request)
        response = admins_ou_manage(context, request)
        self.assertTrue(response['ou_manage_form'].startswith('<form'))

        # 7 - Edit user OUs
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        data = ('_charset_::UTF-8\n'
            + '__formid__::deform\n'
            + '_submit::_submit\n'
            + '__start__::perms:sequence\n'
            + '__start__::permissions:mapping\n'
            + 'ou_selected::' + str(domain_1['_id']) +'\n'
            + '__start__::permission:sequence\n'
            + 'checkbox::MANAGE\n'
            + '__end__::permission:sequence\n'
            + '__end__::permissions:mapping\n'
            + '__end__::perms:sequence\n'
        )
        
        request = self.get_dummy_request()
        request.POST = MockDeformData(data)
        request.matchdict = { 'username': 'newuser' }
        context = LoggedFactory(request)
        response = admins_ou_manage(context, request)
        
        self.assertTrue(isinstance(response, HTTPFound))

        newuser = db.adminusers.find_one({'username': 'newuser'})
        self.assertEqual(newuser['ou_managed'], [str(domain_1['_id'])])


        # 8 - Check the view to change the administrator user settings
        request = self.get_dummy_request()
        request.matchdict = { 'username': 'newuser' }
        context = LoggedFactory(request)
        response = admins_set_variables(context, request)
        self.assertTrue(response['variables_form'].startswith('<form'))


        # 9 - Edit user settings
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        data = ('_charset_::UTF-8\n'
            + '__formid__::deform\n'
            + '_submit::_submit\n'
            + 'nav_tree_pagesize::10\n'
            + 'policies_pagesize::8\n'
            + 'jobs_pagesize::30\n'
            + 'group_nodes_pagesize::10\n'
            + 'uri_ntp::hora.roa.es\n'
            + 'auth_type::LDAP\n'
            + '__start__::auth_ldap:mapping\n'
            + 'uri::URL_LDAP\n'
            + 'base::OU_BASE_USER\n'
            + 'basegroup::OU_BASE_GROUP\n'
            + 'binddn::USER_WITH_BIND_PRIVILEGES\n'
            + 'bindpwd::PASSWORD_USER_BIND\n'
            + '__end__::auth_ldap:mapping\n'
            + '__start__::auth_ad:mapping\n'
            + 'fqdn::\n'
            + 'workgroup::\n'
            + '__end__::auth_ad:mapping\n'
            + '__start__::gem_repos:sequence\n'
            + '__end__::gem_repos:sequence\n'
        )
        
        request = self.get_dummy_request()
        request.POST = MockDeformData(data)
        request.matchdict = { 'username': 'newuser' }
        context = LoggedFactory(request)
        response = admins_set_variables(context, request)
        
        self.assertTrue(isinstance(response, HTTPFound))

        newuser = db.adminusers.find_one({'username': 'newuser'})
        self.assertEqual(newuser['variables']['uri_ntp'], 'hora.roa.es')

        # 10 - Borrado del administrador
        request = self.get_dummy_request()
        request.GET = { 'username': 'newuser' }
        request.method = 'DELETE'
        request.session = {'auth.userid': 'test'}
        context = LoggedFactory(request)
        response = admin_delete(context, request)
        self.assertEqual(response['ok'], 'ok')
        
        # Check the user list
        request = self.get_dummy_request()
        request.GET = { 'q': 'newuser' }
        context = LoggedFactory(request)
        response = admins(context, request)
        admin_users = list(response['admin_users'])
        self.assertEqual(len(admin_users), 0)



    @mock.patch('gecoscc.models.get_chef_api')    
    @mock.patch('gecoscc.utils._get_chef_api')    
    @mock.patch('gecoscc.views.admins._')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.models.gettext')
    @mock.patch('gecoscc.i18n.gettext')
    @mock.patch('gecoscc.views.admins.Maintenance')
    def test_04_maintenance_mode(self, maintenancemodel,
                         gettext, gettext_forms, gettext_models,
                        gettext_i18n, get_chef_api_method,
                        get_chef_api_models_method):
        '''
        Test 4: Enable and distable the maintenance mode
        '''
        if DISABLE_TESTS: return
        
        maintenancemodel.side_effect = MaintenanceMock
        gettext.side_effect = gettext_mock
        gettext_forms.side_effect = gettext_mock
        gettext_models.side_effect = gettext_mock
        gettext_i18n.side_effect = gettext_mock
        get_chef_api_method.side_effect = _get_chef_api_mock
        get_chef_api_models_method.side_effect = get_chef_api_mock
        
        db = self.get_db()

        # 1 - Create request check the maintenance mode
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = admin_maintenance(context, request)

        # Check the response
        self.assertEqual(response['maintenance'], False)

        
        # 2 - Enable the maintenance mode
        data = {
            'mode': 'true',
        }
        
        request = self.get_dummy_request()
        request.GET = data
        context = LoggedFactory(request)
        response = admin_maintenance(context, request)

        # Check if is enabled
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = admin_maintenance(context, request)
        self.assertEqual(response['maintenance'], True)

        # Change the message        
        request = self.get_dummy_request()
        request.POST = {
            '_submit': '_submit',
            'maintenance_message': 'Because is a test!'
        }
        context = LoggedFactory(request)
        response = admin_maintenance(context, request)
        
        # Check if is enabled
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = admin_maintenance(context, request)
        self.assertEqual(response['maintenance'], True)


        # 2 - Enable the maintenance mode
        data = {
            'mode': 'false'
        }
        
        request = self.get_dummy_request()
        request.GET = data
        context = LoggedFactory(request)
        response = admin_maintenance(context, request)
        
        # Check if is disabled
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = admin_maintenance(context, request)
        self.assertEqual(response['maintenance'], False)



    @mock.patch('gecoscc.models.get_chef_api')    
    @mock.patch('gecoscc.utils._get_chef_api')    
    @mock.patch('gecoscc.views.admins._')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.models.gettext')
    @mock.patch('gecoscc.i18n.gettext')
    def test_05_statistics(self, gettext, gettext_forms, gettext_models,
                        gettext_i18n, get_chef_api_method,
                        get_chef_api_models_method):
        '''
        Test 5: Get system statistics
        '''
        if DISABLE_TESTS: return
        
        gettext.side_effect = gettext_mock
        gettext_forms.side_effect = gettext_mock
        gettext_models.side_effect = gettext_mock
        gettext_i18n.side_effect = gettext_mock
        get_chef_api_method.side_effect = _get_chef_api_mock
        get_chef_api_models_method.side_effect = get_chef_api_mock
        
        # 1 - Create request check the maintenance mode
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = statistics(context, request)

        object_counters = list(response['object_counters'])
        user_count = None
        for c in object_counters:
            if c['_id'] == 'user':
                user_count = c

        # Check the response
        self.assertEqual(user_count['count'], 1)


    def test_06_resports_main(self):
        '''
        Test 6: Main reports page
        '''
        if DISABLE_TESTS: return
        
        # 1 - Create request to get the data to print the main
        # reports page (a menu to other reports)
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = reports(context, request)

        # Check the response
        self.assertEqual(response['is_superuser'], True)


    @mock.patch('gecoscc.views.report_audit._')
    def test_07_resports_audit(self, gettext_method):
        '''
        Test 7: Audit log
        '''
        if DISABLE_TESTS: return
        
        gettext_method.side_effect = gettext_mock

        
        # 1 - Create request to get the report in HTML format
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = report_audit_html(context, request)

        # Check the response
        self.assertEqual(response['report_type'], 'html')


    @mock.patch('gecoscc.views.report_computer._')
    def test_08_resports_computers(self, gettext_method):
        '''
        Test 8: Computers report
        '''
        if DISABLE_TESTS: return
        
        gettext_method.side_effect = gettext_mock

        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        
        # 1 - Create request to get the report in HTML format
        request = self.get_dummy_request()
        request.GET = { 'ou_id': str(domain_1['_id'])}
        context = LoggedFactory(request)
        response = report_computer_html(context, request)

        # Check the response
        self.assertEqual(response['report_type'], 'html')


    @mock.patch('gecoscc.views.report_no_computer_users._')
    def test_09_resports_no_computers_users(self, gettext_method):
        '''
        Test 9: Users without computers
        '''
        if DISABLE_TESTS: return
        
        gettext_method.side_effect = gettext_mock

        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        
        # 1 - Create request to get the report in HTML format
        request = self.get_dummy_request()
        request.GET = { 'ou_id': str(domain_1['_id'])}
        context = LoggedFactory(request)
        response = report_no_computer_users_html(context, request)

        # Check the response
        self.assertEqual(response['report_type'], 'html')


    @mock.patch('gecoscc.views.report_no_user_computers._')
    def test_10_resports_no_user_computers(self, gettext_method):
        '''
        Test 10: Computers without users 
        '''
        if DISABLE_TESTS: return
        
        gettext_method.side_effect = gettext_mock

        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        
        # 1 - Create request to get the report in HTML format
        request = self.get_dummy_request()
        request.GET = { 'ou_id': str(domain_1['_id'])}
        context = LoggedFactory(request)
        response = report_no_user_computers_html(context, request)

        # Check the response
        self.assertEqual(response['report_type'], 'html')


    @mock.patch('gecoscc.views.report_permission._')
    def test_11_resports_permissions(self, gettext_method):
        '''
        Test 11: Permissions report 
        '''
        if DISABLE_TESTS: return
        
        gettext_method.side_effect = gettext_mock

        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        
        # 1 - Create request to get the report in HTML format
        request = self.get_dummy_request()
        request.GET = { 'ou_id': str(domain_1['_id'])}
        context = LoggedFactory(request)
        response = report_permission_html(context, request)

        # Check the response
        self.assertEqual(response['report_type'], 'html')

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.views.report_printers._')
    def test_12_resports_printers(self, gettext_method,
        get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 12: Printers report 
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_cookbook_method=get_cookbook_method,
            get_cookbook_method_tasks=get_cookbook_method_tasks)
        gettext_method.side_effect = gettext_mock

        data, new_printer = self.create_printer('Testprinter')

        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        
        # 1 - Create request to get the report in HTML format
        request = self.get_dummy_request()
        request.GET = { 'ou_id': str(domain_1['_id'])}
        context = LoggedFactory(request)
        response = report_printers_html(context, request)

        # Check the response
        self.assertEqual(response['report_type'], 'html')

    @mock.patch('gecoscc.views.report_status._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    @mock.patch('gecoscc.utils._get_chef_api')    
    def test_13_resports_status(self, get_chef_api_method, get_cookbook_method,
        get_cookbook_method_tasks, NodeClass, ChefNodeClass, TaskNodeClass,
        ClientClass, isinstance_method, gettext_method):
        '''
        Test 13: Status report 
        '''
        if DISABLE_TESTS: return
        
        self.apply_mocks(get_chef_api_method, get_cookbook_method,
            get_cookbook_method_tasks, NodeClass, ChefNodeClass,
            isinstance_method, TaskNodeClass=TaskNodeClass,
            ClientClass=ClientClass, gettext=gettext_method)
        self.cleanErrorJobs()
                                
        self.register_computer()

        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        
        # 1 - Create request to get the report in HTML format
        request = self.get_dummy_request()
        request.GET = { 'ou_id': str(domain_1['_id'])}
        context = LoggedFactory(request)
        response = report_status_html(context, request)

        # Check the response
        self.assertEqual(response['report_type'], 'html')


    @mock.patch('gecoscc.views.report_user._')
    def test_14_resports_user(self, gettext_method):
        '''
        Test 14: User report 
        '''
        if DISABLE_TESTS: return
        
        gettext_method.side_effect = gettext_mock

        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        
        # 1 - Create request to get the report in HTML format
        request = self.get_dummy_request()
        request.GET = { 'ou_id': str(domain_1['_id'])}
        context = LoggedFactory(request)
        response = report_user_html(context, request)

        # Check the response
        self.assertEqual(response['report_type'], 'html')



    @mock.patch('gecoscc.views.report_storages._')
    def test_15_reports_storages(self, gettext_method):
        '''
        Test 15: Storages reports 
        '''
        if DISABLE_TESTS: return
        
        gettext_method.side_effect = gettext_mock

        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        
        # 1 - Create request to get the report in HTML format
        request = self.get_dummy_request()
        request.GET = { 'ou_id': str(domain_1['_id'])}
        context = LoggedFactory(request)
        response = report_storages_html(context, request)

        # Check the response
        self.assertEqual(response['report_type'], 'html')



    @mock.patch('socket.gethostbyname')
    def test_16_server_status(self, gethostbyname_method):
        '''
        Test 16: Server status 
        '''
        if DISABLE_TESTS: return
        

        # 1 - Get the server status
        request = self.get_dummy_request()
        request.GET = {}
        context = LoggedFactory(request)
        response = internal_server_status(context, request)

        # Check the response
        self.assertTrue('cpu' in response)


        # 2 - Get server connections
        request = self.get_dummy_request()
        request.GET = {}
        context = LoggedFactory(request)
        response = internal_server_connections(context, request)

        # Check the response
        self.assertEqual(response, [])
