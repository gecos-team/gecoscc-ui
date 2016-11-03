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

import json
import unittest
import sys

import mock

from copy import copy, deepcopy

from bson import ObjectId
from celery import current_app
from chef.node import NodeAttributes
from cornice.errors import Errors
from paste.deploy import loadapp
from pymongo import Connection
from pyramid import testing
from pyramid.httpexceptions import HTTPForbidden

from api.chef_status import USERS_OHAI
from gecoscc.api.organisationalunits import OrganisationalUnitResource
from gecoscc.api.chef_status import ChefStatusResource
from gecoscc.api.computers import ComputerResource
from gecoscc.api.groups import GroupResource
from gecoscc.api.printers import PrinterResource
from gecoscc.api.repositories import RepositoryResource
from gecoscc.api.storages import StorageResource
from gecoscc.api.users import UserResource
from gecoscc.api.register_computer import RegisterComputerResource
from gecoscc.commands.import_policies import Command as ImportPoliciesCommand
from gecoscc.commands.create_software_profiles import Command as ImportSoftwareProfilesCommand
from gecoscc.commands.recalc_nodes_policies import Command as RecalcNodePoliciesCommand
from gecoscc.db import get_db
from gecoscc.userdb import get_userdb
from gecoscc.permissions import LoggedFactory, SuperUserFactory
from gecoscc.views.portal import home
from gecoscc.views.admins import admin_add

# This url is not used, every time the code should use it, the code is patched
# and the code use de NodeMock class
CHEF_URL = 'https://CHEF_URL/'
CHEF_NODE_ID = '36e13492663860e631f53a00afcdd92d'


def create_chef_admin_user_mock(api, settings, username, password=None, email='nobody@nobody.es'):
    pass


def gettext_mock(string, *args, **kwargs):
    return string


def get_cookbook_mock(api, cookbook_name):
    '''
    Returns a static cookbook saved in  json file
    If the cookbook change the cookbook.json should be updated
    '''
    cook_book_json = open('gecoscc/test_resources/cookbook.json').read().replace('%(chef_url)s', CHEF_URL)
    return json.loads(cook_book_json)


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
        return NodeAttributesMock(self.data.__getitem__(key), self.node, self.node_attr_type)

    def __iter__(self):
        return self.data.__iter__()

    def __delitem__(self, key):
        return self.data.__delitem__(key)

    def __nonzero__(self):
        return bool(self.data)


class NodeMock(object):

    '''
    NodeMock emulates NodeAttributes <chef.node.Node>
    With this class and the two previous classes the chef client and chef server are emulated
    '''

    def __init__(self, chef_node_id, api):
        super(NodeMock, self).__init__()
        self.name = chef_node_id
        node_default_json = open('gecoscc/test_resources/node_default.json').read().replace(
            '%(chef_url)s', CHEF_URL).replace('%s(node_name)s', chef_node_id)
        self.default = NodeAttributesMock(json.loads(node_default_json), self, 'default')

        if chef_node_id in NODES:
            self.attributes = NodeAttributesMock(copy(NODES[chef_node_id]), self)
            self.normal = self.attributes
            self.exists = True
        else:
            node_attributes_json = open('gecoscc/test_resources/node_attributes.json').read().replace(
                '%(chef_url)s', CHEF_URL).replace('%s(node_name)s', chef_node_id)

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
        return self.attributes.get(key, default)

    def save(self):
        NODES[self.name] = copy(self.attributes.data)
        self.exists = True

    def delete(self):
        del NODES[self.name]


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
        app_sec = 'config:config-templates/test.ini'
        name = None
        relative_to = '.'
        kw = {'global_conf': {}}
        config = loadapp(app_sec, name=name, relative_to=relative_to, **kw)
        self.config = config
        testing.setUp(config.application.registry)
        current_app.add_defaults(config.application.registry.settings)
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
        c = Connection()
        db_name = self.config.application.registry.settings['mongodb'].database_name
        c.drop_database(db_name)

    def drop_mock_nodes(self):
        '''
        Useful method, drop mock nodes
        '''
        global NODES
        NODES = {}

    def get_dummy_request(self, is_superuser=True):
        '''
        Useful method, returns a typical request, with the same request properties
        than pyramid add (see gecoscc/__init__)
        '''
        request = testing.DummyRequest()
        request.db = get_db(request)
        request.userdb = get_userdb(request)
        if is_superuser is True:
            user = request.db.adminusers.find_one({'is_superuser': True})
            if not user:
                user = request.userdb.create_user('test', 'test', 'test@example.com', {'is_superuser': True})
            request.user = request.db.adminusers.find_one({'is_superuser': True})
        else:
            user = request.db.adminusers.find_one({'is_superuser': False})
            if not user:
                user = request.userdb.create_user('test_no_super', 'test_no_super', 'test_no_super@example.com', {'is_superuser': False})
            request.user = request.db.adminusers.find_one({'is_superuser': False})

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

    def get_dummy_json_put_request(self, data, schema=None, is_superuser=True):
        '''
        Useful method, returns a typical put request
        '''
        request = self.get_dummy_request(is_superuser)
        request.method = 'PUT'
        request.errors = Errors()
        if schema:
            if isinstance(data['_id'], basestring):
                data['_id'] = ObjectId(data['_id'])
            serialize_data = schema().serialize(data)
            request.validated = deepcopy(serialize_data)
            request.matchdict['oid'] = request.validated['_id']
            request.validated['_id'] = ObjectId(request.validated['_id'])

            node_type = data.get('type', '')
            data_validated_hook = getattr(self, 'data_validated_hook_%s' % node_type, None)
            if data_validated_hook:
                data_validated_hook(request.validated)

        request.json = json.dumps(serialize_data)
        request.path = '/api/%ss/%s/' % (serialize_data['type'], serialize_data['_id'])
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
            if isinstance(comp_id, basestring):
                data['computers'][i] = ObjectId(comp_id)
        for i, comp in enumerate(data.get('memberof', [])):
            comp_id = data['memberof'][i]
            if isinstance(comp_id, basestring):
                data['memberof'][i] = ObjectId(comp_id)

    def data_validated_hook_computer(self, data):
        for i, member in enumerate(data.get('memberof', [])):
            member_id = data['memberof'][i]
            if isinstance(member_id, basestring):
                data['memberof'][i] = ObjectId(member_id)

    def data_validated_hook_group(self, data):
        for i, comp in enumerate(data.get('members', [])):
            comp_id = data['members'][i]
            if isinstance(comp_id, basestring):
                data['members'][i] = ObjectId(comp_id)

    def assertNoErrorJobs(self):
        '''
        Useful method, check there are not any job with error (or even success)
        every job should be "processing"
        '''
        db = self.get_db()
        self.assertEqual(db.jobs.find({'status': {'$ne': 'processing'}}).count(),
                         0)

    def assertEmitterObjects(self, node_policy, db_emiters, fields):
        '''
        Useful method, check if the second list has the same values than the first
        '''
        node_policy.sort(key=lambda e: e['uri'])
        db_emiters.sort(key=lambda e: e['uri'])

        for i, emiter in enumerate(db_emiters):
            self.assertEqualsObjects(node_policy[i], emiter, fields=fields)

    def assertEqualsObjects(self, data, new_data, schema_data=None, schema_new_data=None, fields=None):
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
    def create_basic_structure(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        1. Create a flag (organisational unit level 0)
        2. Create a domain (organisational unit level 1)
        3. Create a organisational unit
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        data = {'name': 'Flag',
                'type': 'ou',
                'path': 'root',
                'source': 'gecos'}

        request_post = self.get_dummy_json_post_request(data, OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request_post)
        flag_new = ou_api.collection_post()

        data, domain = self.create_domain('Domain 1', flag_new)
        data, ou = self.create_ou('OU 1')

    @mock.patch('gecoscc.commands.import_policies.get_cookbook')
    def import_policies(self, get_cookbook_method):
        '''
        Useful method, import the policies
        '''

        get_cookbook_method.side_effect = get_cookbook_mock
        argv_bc = sys.argv
        sys.argv = ['pmanage', 'config-templates/test.ini', 'import_policies',
                    '-a', 'test', '-k', 'gecoscc/test_resources/media/users/test/chef_client.pem']
        command = ImportPoliciesCommand('config-templates/test.ini')
        command.command()
        sys.argv = argv_bc

    def recalc_policies(self):
        '''
        Useful method, recalculate policies
        '''
        argv_bc = sys.argv
        sys.argv = ['pmanage', 'config-templates/test.ini', 'recalc_nodes_policies',
                    '-a', 'test']
        command = RecalcNodePoliciesCommand('config-templates/test.ini')
        command.command()
        sys.argv = argv_bc

    def import_profile_software(self):
        '''
        Useful method, import software software_profiles
        '''
        argv_bc = sys.argv
        sys.argv = ['pmanage', 'config-templates/test.ini', 'create_software_profiles']
        command = ImportSoftwareProfilesCommand('config-templates/test.ini')
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
        return self.create_node(data, OrganisationalUnitResource, ou_name=domain_name)

    def create_domain(self, ou_name, flag):
        '''
        Useful method, create a Domain
        '''
        data = {'name': ou_name,
                'type': 'ou',
                'path': '%s,%s' % (flag['path'], flag['_id']),
                'master': 'gecos',
                'source': 'gecos'}
        return self.create_node(data, OrganisationalUnitResource, ou_name=flag['name'])

    def create_node(self, data, api_class, ou_name='OU 1'):
        '''
        Useful method, create a node
        '''
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': ou_name})

        data['path'] = '%s,%s' % (ou_1['path'], ou_1['_id'])

        request_post = self.get_dummy_json_post_request(data, api_class.schema_detail)
        object_api = api_class(request_post)

        return (data, object_api.collection_post())

    def update_node(self, obj, field_name, field_value, api_class, is_superuser=True):
        '''
        Useful method, update a node
        '''
        if isinstance(obj[field_name], list):
            obj[field_name].append(field_value)
        else:
            obj[field_name] = field_value
        request_put = self.get_dummy_json_put_request(obj, api_class.schema_detail, is_superuser)
        api = api_class(request_put)
        return api.put()

    def delete_node(self, node, api_class):
        '''
        Useful method, delete a node
        '''
        request = self.dummy_get_request(node, api_class.schema_detail)
        node_api = api_class(request)
        node = node_api.get()

        request_delete = self.get_dummy_delete_request(node, api_class.schema_detail)
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

    def add_admin_user(self, username):
        '''
        Userful method, register an admin User
        '''
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
        request = self.get_dummy_request()
        data = {'gcc_username': gcc_superusername,
                'node_id': node.name}
        request.POST = data
        chef_status_api = ChefStatusResource(request)
        chef_status_response = chef_status_api.put()
        self.assertEqual(chef_status_response['ok'], True)

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
        request_put = self.get_dummy_json_put_request(node, api_class.schema_detail)
        node_api = api_class(request_put)
        node_update = node_api.put()
        if node_update is not None:
            self.assertEqualsObjects(node, node_update, api_class.schema_detail)

        node = NodeMock(chef_node_id, None)
        try:
            node_policy = node.attributes.get_dotted(policy_path)
        except KeyError:
            node_policy = []
        return node_policy

    def remove_policy_and_get_dotted(self, node, chef_node_id, api_class, policy_path):
        '''
        Useful method, remove policy from node and return dotted
        '''
        node['policies'] = {}
        request_put = self.get_dummy_json_put_request(node, api_class.schema_detail)
        node_api = api_class(request_put)
        node_updated = node_api.put()
        self.assertEqualsObjects(node, node_updated, api_class.schema_detail)
        node = NodeMock(chef_node_id, None)
        return node.attributes.get_dotted(policy_path)

    def get_default_policies(self):
        policies = {"package_res_policy": {'policy': self.get_default_ws_policy(),
                                           'path': self.get_default_ws_policy()['path'] + '.package_list',
                                           'policy_data_node_1': {'package_list': ['gimp'], 'pkgs_to_remove': []},
                                           'policy_data_node_2': {'package_list': ['libreoffice'], 'pkgs_to_remove': []}},
                    "remote_shutdown_res": {'policy': self.get_default_ws_policy(slug='remote_shutdown_res'),
                                            'path': self.get_default_ws_policy(slug='remote_shutdown_res')['path'] + '.shutdown_mode',
                                            'policy_data_node_1': {'shutdown_mode': 'reboot'},
                                            'policy_data_node_2': {'shutdown_mode': 'halt'}}}
        return policies

    def get_default_policies_user(self):
        policies = {"user_apps_autostart_res": {'policy': self.get_default_user_policy(slug='user_apps_autostart_res'),
                                                'path': self.get_default_user_policy(slug="user_apps_autostart_res")['path'] + '.users.',
                                                'policy_data_node_1': {"desktops": ["kate"]},
                                                'policy_data_node_2': {"desktops": ["sublime"]}},
                    "desktop_background_res": {'policy': self.get_default_user_policy(slug='desktop_background_res'),
                                               'path': self.get_default_user_policy(slug="desktop_background_res")['path'] + '.users.',
                                               'policy_data_node_1': {"desktop_file": "mountain.png"},
                                               'policy_data_node_2': {"desktop_file": "river.png"}}}
        return policies

    def apply_mocks(self, get_cookbook_method=None, get_cookbook_method_tasks=None, NodeClass=None,
                    ChefNodeClass=None, isinstance_method=None, gettext=None, create_chef_admin_user_method=None,
                    ChefNodeStatusClass=None, TaskNodeClass=None, TaskClientClass=None, ClientClass=None):
        '''
        mocks
        '''
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
            create_chef_admin_user_method.side_effect = create_chef_admin_user_mock
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
        self.apply_mocks(get_cookbook_method=get_cookbook_method, get_cookbook_method_tasks=get_cookbook_method_tasks)
        self.assertIsPaginatedCollection(api_class=PrinterResource)

        # 1 - Create printer
        data, new_printer = self.create_printer('Testprinter')

        # 2 - Verification that the printers has been created successfully
        self.assertEqualsObjects(data, new_printer)

        # 3 - Update printer's description
        printer_updated = self.update_node(obj=new_printer, field_name='description',
                                           field_value=u'Test', api_class=PrinterResource)

        # 4 - Verification that printer's description has been updated successfully
        self.assertEqualsObjects(new_printer, printer_updated, PrinterResource.schema_detail)

        # 5 - Delete printer
        self.delete_node(printer_updated, PrinterResource)

        # 6 - Verification that the printers has been deleted successfully
        self.assertDeleted(field_name='name', field_value='Printer tests')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_03_shared_folder(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 3: Create, update and delete a shared folder
        '''
        self.apply_mocks(get_cookbook_method=get_cookbook_method, get_cookbook_method_tasks=get_cookbook_method_tasks)
        self.assertIsPaginatedCollection(api_class=StorageResource)

        # 1 - Create shared folder
        data, new_folder = self.create_storage('test_storage')

        # 2 - Verification that the shared folder has been created successfully
        self.assertEqualsObjects(data, new_folder)

        # 3 - Update shared folder's URI
        folder_updated = self.update_node(obj=new_folder, field_name='uri', field_value=u'Test',
                                          api_class=StorageResource)
        # 4 - Verification that shared folder's URI has been updated successfully
        self.assertEqualsObjects(new_folder, folder_updated, StorageResource.schema_detail)

        # 5 - Delete shared folder
        self.delete_node(folder_updated, StorageResource)

        # 6 - Verification that the shared folder has been deleted successfully
        self.assertDeleted(field_name='name', field_value='Folder tests')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_04_repository(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 4: Create, update and delete a repository
        '''
        self.apply_mocks(get_cookbook_method=get_cookbook_method, get_cookbook_method_tasks=get_cookbook_method_tasks)
        self.assertIsPaginatedCollection(api_class=RepositoryResource)
        # 1 - Create repository
        data, new_repository = self.create_repository('Repo')

        # 2 - Verification that the repository has been created successfully
        self.assertEqualsObjects(data, new_repository)

        # 3 - Update repository's URI
        repository_update = self.update_node(obj=new_repository, field_name='uri',
                                             field_value=u'Test', api_class=RepositoryResource)

        # 4 - Verification that shared folder's URI has been updated successfully
        self.assertEqualsObjects(new_repository, repository_update, RepositoryResource.schema_detail)

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
        self.apply_mocks(get_cookbook_method=get_cookbook_method, get_cookbook_method_tasks=get_cookbook_method_tasks)
        self.assertIsPaginatedCollection(api_class=UserResource)
        # 1 - Create user
        data, new_user = self.create_user('testuser')

        # 2 - Verification that the user has been created successfully
        self.assertEqualsObjects(data, new_user)

        # 3 - Update user's first name
        user_updated = self.update_node(obj=new_user, field_name='first_name',
                                        field_value=u'Another name', api_class=UserResource)

        # 4 - Verification that user's first name has been updated successfully
        self.assertEqualsObjects(new_user, user_updated, UserResource.schema_detail)

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
        self.apply_mocks(get_cookbook_method=get_cookbook_method, get_cookbook_method_tasks=get_cookbook_method_tasks)
        self.assertIsPaginatedCollection(api_class=GroupResource)
        # 1 - Create group
        data, new_group = self.create_group('testgroup')

        # 2 - Verification that the group has been created successfully
        self.assertEqualsObjects(data, new_group)

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
    def test_07_computer(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass,
                         ChefNodeClass, TaskNodeClass, ClientClass, isinstance_method):
        '''
        Test 7: Create, update and delete a computer
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, TaskNodeClass=TaskNodeClass, ClientClass=ClientClass)

        # 1 - Register workstation
        self.register_computer()

        # 2  Verification that the workstation has been registered successfully
        computer = self.get_db().nodes.find_one({'name': 'testing'})

        # 3 Update workstation's type
        request = self.get_dummy_request()
        computer_api = ComputerResource(request)
        computer = computer_api.collection_get()
        computer_updated = self.update_node(obj=computer['nodes'][0], field_name='family',
                                            field_value=u'laptop', api_class=ComputerResource)

        # 4 - Verification that the workstation's type has been udpated successfully
        self.assertEqualsObjects(computer['nodes'][0], computer_updated, ComputerResource.schema_detail)

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
        self.apply_mocks(get_cookbook_method=get_cookbook_method, get_cookbook_method_tasks=get_cookbook_method_tasks)
        self.assertIsPaginatedCollection(api_class=OrganisationalUnitResource)
        # 1 - Create OU
        data, new_ou = self.create_ou('OU 2')

        # 2 - Verification that the OU has been created successfully
        self.assertEqualsObjects(data, new_ou)

        # 3 - Update OU's extra
        ou_updated = self.update_node(obj=new_ou,
                                      field_name='extra',
                                      field_value=u'Test',
                                      api_class=OrganisationalUnitResource)

        # 4 - Verification that OU has been updated successfully
        self.assertEqualsObjects(new_ou, ou_updated, OrganisationalUnitResource.schema_detail)

        # 5 - Delete OU
        self.delete_node(ou_updated, OrganisationalUnitResource)

        # 6 - Verification that the OU has been deleted successfully
        self.assertDeleted(field_name='extra', field_value='Test')

        self.assertNoErrorJobs()


class AdvancedTests(BaseGecosTestCase):

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_01_update_resources_user(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                      isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 1:
        1. Check the shared_folder policy works using users
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)

        # 5 - Add storage to user and check if it is applied in chef node
        user = db.nodes.find_one({'name': username})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        storage_policy = db.policies.find_one({'slug': 'storage_can_view'})

        user['policies'] = {unicode(storage_policy['_id']): {'object_related_list': [new_storage['_id']]}}
        policy_path = storage_policy['path'] + '.' + username + '.gtkbookmarks'
        node_policy = self.add_and_get_policy(node=user, chef_node_id=chef_node_id, api_class=UserResource, policy_path=policy_path)

        # 6 - Verification if the storage is applied to user in chef node
        self.assertEqualsObjects(node_policy[0], new_storage, fields=('name',
                                                                      'uri'))

        # 7 - Update storage's URI
        storage_update = self.update_node(obj=new_storage, field_name='uri',
                                          field_value='http://modify.storage.com', api_class=StorageResource)
        node = NodeMock(chef_node_id, None)

        # 8 - Verification that the storage has been updated successfully in chef node
        node_policy = node.attributes.get_dotted(policy_path)
        self.assertEqualsObjects(node_policy[0], storage_update, fields=('name',
                                                                         'uri'))
        # 9 Create stgorage
        data, new_storage_2 = self.create_storage('shared folder mergeable')

        # 10 Add storage to OU and check if it's applied in chef node
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        ou_1['policies'] = {unicode(storage_policy['_id']): {'object_related_list': [new_storage_2['_id']]}}
        node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_path)

        # 11 - Verification if the storage is applied to user in chef node
        self.assertEmitterObjects(node_policy, [storage_update, new_storage_2], fields=('name',
                                                                                        'uri'))

        # 12 - Delete storage and verification that the storage has beed deleted successfully in chef node
        node_policy = self.remove_policy_and_get_dotted(user, chef_node_id, UserResource, policy_path)
        self.assertEqualsObjects(node_policy[0], new_storage_2, fields=('name',
                                                                        'uri'))

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_02_update_resources_workstation(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                             isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 2:
        1. Check the printer policy works using workstation
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # 1 - Create printer
        db = self.get_db()
        data, new_printer = self.create_printer('printer test')

        # 2 - Register workstation
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Add printer to workstation and check if it is applied in chef node
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer, ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()

        printer_policy = db.policies.find_one({'slug': 'printer_can_view'})
        computer['policies'] = {unicode(printer_policy['_id']): {'object_related_list': [new_printer['_id']]}}
        policy_path = printer_policy['path']
        node_policy = self.add_and_get_policy(node=computer, chef_node_id=chef_node_id, api_class=ComputerResource, policy_path=policy_path)

        # 4 - Verification if the printer is applied to workstation in chef node
        self.assertEqualsObjects(node_policy[0], new_printer, fields=('oppolicy',
                                                                      'model',
                                                                      'uri',
                                                                      'name',
                                                                      'manufacturer'))

        # 5 - Modify printer's URI and check if is applied in chef node
        node = NodeMock(chef_node_id, None)
        printer_update = self.update_node(obj=new_printer, field_name='uri',
                                          field_value='http://modifiy.example.com', api_class=PrinterResource)
        node_policy = node.attributes.get_dotted(policy_path)

        # 6 - Verification that the printer's URI has been updated successfully in chef node
        self.assertEqualsObjects(node_policy[0], printer_update, fields=('oppolicy',
                                                                         'model',
                                                                         'uri',
                                                                         'name',
                                                                         'manufacturer'))

        # 7 - Create printer
        db = self.get_db()
        data, new_printer_2 = self.create_printer('printer mergeable')

        # 8 - Add printer to workstation and check if it is applied in chef node
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        ou_1['policies'] = {unicode(printer_policy['_id']): {'object_related_list': [new_printer_2['_id']]}}
        policy_path = printer_policy['path']
        node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_path)

        # 9 - Verification that the printer's URI has been updated successfully in chef node
        self.assertEmitterObjects(node_policy, [new_printer_2, printer_update], fields=('oppolicy',
                                                                                        'model',
                                                                                        'uri',
                                                                                        'name',
                                                                                        'manufacturer'))

        # 10 - Delete printer and check if the chef node has been updated
        self.delete_node(printer_update, PrinterResource)
        self.assertDeleted(field_name='name', field_value='printer test')
        printer_policy = node.attributes.get_dotted(policy_path)
        self.assertEqualsObjects(printer_policy[0], new_printer_2, fields=('oppolicy',
                                                                           'model',
                                                                           'uri',
                                                                           'name',
                                                                           'manufacturer'))
        self.assertNoErrorJobs()

    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_03_priority_ous_workstation(self, get_cookbook_method, get_cookbook_method_tasks,
                                         NodeClass, ChefNodeClass, isinstance_method):
        '''
        Test 3:
        1. Check the registration work station works
        2. Check the policies pripority works using organisational unit
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method)

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
            ou_1['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
            node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policies[policy]['path'])

            # 3 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['package_list'])
            else:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

            # 4 - Add policy in domain
            domain_1['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_2']}
            domain_policy = self.add_and_get_policy(node=domain_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policies[policy]['path'])

            if policies[policy]['policy']['is_mergeable']:
                # 5 - Verification if OU's and Domain's policy is applied in chef node
                self.assertEquals(domain_policy, ['libreoffice', 'gimp'])
                # 6 - Remove OU's policy and verification if Domain's policy is applied in chef node
                policy_applied = self.remove_policy_and_get_dotted(ou_1, chef_node_id, OrganisationalUnitResource, policies[policy]['path'])
                self.assertEquals(policy_applied, ['libreoffice'])
                # 7 - Remove policy in domain and check if domain_1's policy isn't applied in chef node
                policy_applied = self.remove_policy_and_get_dotted(domain_1, chef_node_id, OrganisationalUnitResource, policies[policy]['path'])
                self.assertEquals(policy_applied, [])
                # 8, 9 - Add policy to workstation and verification if ws's policy has been applied successfully
                computer = db.nodes.find_one({'name': 'testing'})
                computer['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
                node_policy = self.add_and_get_policy(node=computer, chef_node_id=chef_node_id, api_class=ComputerResource, policy_path=policies[policy]['path'])
                self.assertEquals(node_policy, ['gimp'])
                # 10 - Add policy in OU
                ou_1['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
                node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policies[policy]['path'])
                # 11 - Create workstation
                self.register_computer(chef_node_id='36e13492663860e631f53a00afcsi29f')
            else:
                # 5  Verification if OU's policy is applied in chef node
                self.assertEquals(domain_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])
                # 6 - Remove OU's policy and verification if Domain's policy is applied in chef node
                policy_applied = self.remove_policy_and_get_dotted(ou_1, chef_node_id, OrganisationalUnitResource, policies[policy]['path'])
                self.assertEquals(policy_applied, 'halt')
                # 7 - Remove policy in domain and check if domain_1's policy isn't applied in chef node
                policy_applied = self.remove_policy_and_get_dotted(domain_1, chef_node_id, OrganisationalUnitResource, policies[policy]['path'])
                self.assertEquals(policy_applied, '')
                # 8, 9 - Add policy to workstation and verification if ws's policy has been applied successfully
                computer['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
                node_policy = self.add_and_get_policy(node=computer, chef_node_id=chef_node_id, api_class=ComputerResource, policy_path=policies[policy]['path'])
                self.assertEquals(node_policy, 'reboot')
                # 10 - Add policy in OU
                ou_1['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
                node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policies[policy]['path'])
                # 11 - Create workstation
                self.register_computer(chef_node_id='36e13492663860e631f53a023fcsi29f')
            # 3 - Verification that the OU's policy has been applied successfully
            if policies[policy]['policy']['is_mergeable']:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['package_list'])
            else:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_04_priority_user_workstation(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                          isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 4:
        1. Check the registration work station works
        2. Check the policies priority works using organisational unit and user
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 1 - Create user
        username = 'testuser'
        data, new_user = self.create_user(username)
        self.assertEqualsObjects(data, new_user)

        # 2 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Register user in ws
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)

        policies = self.get_default_policies_user()
        user = db.nodes.find_one({'name': username})
        for policy in policies:
            # 4 - Add policy in OU
            ou_1['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
            name_element_policy = policies[policy]['policy_data_node_1']
            policy_path_1 = policies[policy]['path'] + username + '.' + name_element_policy.keys()[0]
            node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_path_1)
            # 5 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['desktops'])
            else:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['desktop_file'])
            # 6 - Add policy in user
            name_element_policy = policies[policy]['policy_data_node_2']
            policy_path_2 = policies[policy]['path'] + username + '.' + name_element_policy.keys()[0]
            user['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_2']}
            node_policy = self.add_and_get_policy(node=user, chef_node_id=chef_node_id, api_class=UserResource, policy_path=policy_path_2)

            if policies[policy]['policy']['is_mergeable']:
                # 7 - Verification if this policy is applied in chef node
                self.assertEquals(node_policy, ['kate', 'sublime'])
            else:
                # 7 - Verification if this policy is applied in chef node
                self.assertEquals(node_policy, policies[policy]['policy_data_node_2']['desktop_file'])
            # Remove policy in OU
            self.remove_policy_and_get_dotted(ou_1, chef_node_id, OrganisationalUnitResource, policy_path_1)

        # 8, 9 - Create user Assign user to workstation
        username = 'usertest'
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})

        for policy in policies:
            # 10 - Add policy in user
            name_element_policy = policies[policy]['policy_data_node_2']
            policy_path_2 = policies[policy]['path'] + username + '.' + name_element_policy.keys()[0]
            user['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_2']}
            node_policy = self.add_and_get_policy(node=user, chef_node_id=chef_node_id, api_class=UserResource, policy_path=policy_path_2)

            if policies[policy]['policy']['is_mergeable']:
                # 11 - Verification if this policy is applied in chef node
                self.assertEquals(node_policy, ['sublime'])
            else:
                # 11 - Verification if this policy is applied in chef node
                self.assertEquals(node_policy, policies[policy]['policy_data_node_2']['desktop_file'])
            # 12 - Add policy in OU
            ou_1['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
            name_element_policy = policies[policy]['policy_data_node_1']
            policy_path_1 = policies[policy]['path'] + username + '.' + name_element_policy.keys()[0]
            node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_path_1)
            if policies[policy]['policy']['is_mergeable']:
                # 13 - Verification if this policy is applied in chef node
                node = NodeMock(chef_node_id, None)
                node_policy = node.attributes.get_dotted(policy_path_1)
                self.assertEquals(node_policy, ['kate', 'sublime'])
            else:
                # 13 - Verification if this policy is applied in chef node
                self.assertEquals(node_policy, policies[policy]['policy_data_node_2']['desktop_file'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_05_priority_workstation_ous_groups(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                                isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 5:
        1. Check the registration work station works
        2. Check the policies priority works using organisational unit and groups
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # 1- Create a group
        data, new_group = self.create_group('testgroup')

        # 2 - Register a workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()
        computer = db.nodes.find_one({'name': 'testing'})

        # 3 - Assign group to computer
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': 'testgroup'})
        self.assertEqual(group['members'][0], computer['_id'])

        policies = self.get_default_policies()
        for policy in policies:
            # 4 - Add policy in OU
            ou_1['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
            node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policies[policy]['path'])

            # 5 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['package_list'])
            else:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

            # 6 -  Add policy in group
            group['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_2']}
            node_policy = self.add_and_get_policy(node=group, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policies[policy]['path'])

            if policies[policy]['policy']['is_mergeable']:
                # 7 - Verification if the policy is applied in chef node
                self.assertEquals(node_policy, ['libreoffice', 'gimp'])
                # 8 - Remove policy in group
                policy_applied = self.remove_policy_and_get_dotted(group, chef_node_id, GroupResource, policies[policy]['path'])

                # 9 - Verification if the OU's policy is applied in chef node
                self.assertEquals(policy_applied, ['gimp'])
            else:
                # 7 - Verification if the policy is applied in chef node
                self.assertEquals(node_policy, policies[policy]['policy_data_node_2']['shutdown_mode'])

                # 8 - Remove policy in group
                policy_applied = self.remove_policy_and_get_dotted(group, chef_node_id, GroupResource, policies[policy]['path'])

                # 9 - Verification if the OU's policy is applied in chef node
                self.assertEquals(policy_applied, 'reboot')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_06_priority_workstation_groups(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                            isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 6:
        1. Check the registration work station works
        2. Check the policies priority works using workstation and groups
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

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
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group_a)

        # 5 - Assign groupB to computer
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group_b)

        # Check if group's node is update in node chef
        group_a = db.nodes.find_one({'name': 'group_A'})
        self.assertEqual(group_a['members'][0], computer['_id'])
        group_b = db.nodes.find_one({'name': 'group_B'})
        self.assertEqual(group_b['members'][0], computer['_id'])

        policies = self.get_default_policies()
        for policy in policies:
            # 6 - Add policy in A group
            group_a['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
            group_a_policy = self.add_and_get_policy(node=group_a, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policies[policy]['path'])

            # 7 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEquals(group_a_policy, policies[policy]['policy_data_node_1']['package_list'])
            else:
                self.assertEquals(group_a_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

            # 8 -  Add policy in B group
            group_b['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_2']}
            group_b_policy = self.add_and_get_policy(node=group_b, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policies[policy]['path'])
            if policies[policy]['policy']['is_mergeable']:
                # 9 - Verification if the policy is applied in chef node
                self.assertEquals(group_b_policy, ['libreoffice', 'gimp'])
                # 10 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a, chef_node_id, GroupResource, policies[policy]['path'])

                # 11 - Verification if the B group's policy is applied in chef node
                self.assertEquals(policy_applied, ['libreoffice'])
            else:
                # 9 - Verification if the policy is applied in chef node
                self.assertEquals(group_b_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

                # 10 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a, chef_node_id, GroupResource, policies[policy]['path'])

                # 11 - Verification if the B group's policy is applied in chef node
                self.assertEquals(policy_applied, 'halt')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_07_priority_workstation_groups_different_ou(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                                         isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 7:
        1. Check the registration work station works
        2. Check the policies priority works using groups in differents OUs
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

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
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group_a)

        # 5 - Assign groupB to computer
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group_b)

        # Check if group's node is update in node chef
        group_a = db.nodes.find_one({'name': new_group_a['name']})
        self.assertEqual(group_a['members'][0], computer['_id'])
        group_b = db.nodes.find_one({'name': new_group_b['name']})
        self.assertEqual(group_b['members'][0], computer['_id'])

        policies = self.get_default_policies()
        for policy in policies:
            # 6 - Add policy in A group
            group_a['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
            group_a_policy = self.add_and_get_policy(node=group_a, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policies[policy]['path'])

            # 7 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEquals(group_a_policy, policies[policy]['policy_data_node_1']['package_list'])
            else:
                self.assertEquals(group_a_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

            # 8 -  Add policy in B group
            group_b['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_2']}
            group_b_policy = self.add_and_get_policy(node=group_b, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policies[policy]['path'])
            if policies[policy]['policy']['is_mergeable']:
                # 9 - Verification if the policy is applied in chef node
                self.assertEquals(group_b_policy, ['libreoffice', 'gimp'])
                # 10 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a, chef_node_id, GroupResource, policies[policy]['path'])

                # 11 - Verification if the B group's policy is applied in chef node
                self.assertEquals(policy_applied, ['libreoffice'])
            else:
                # 9 - Verification if the policy is applied in chef node
                self.assertEquals(group_b_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

                # 10 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a, chef_node_id, GroupResource, policies[policy]['path'])

                # 11 - Verification if the B group's policy is applied in chef node
                self.assertEquals(policy_applied, 'halt')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_08_priority_user_ous_groups(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                         isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 8:
        1. Check the registration work station works
        2. Check the policies priority works using groups and OUs
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)

        # 5 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], user['_id'])

        policies = self.get_default_policies()
        for policy in policies:
            # 6 - Add policy in OU
            ou_1['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
            node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policies[policy]['path'])

            # 7 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['package_list'])
            else:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

            # 8 -  Add policy in group
            group['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_2']}
            node_policy = self.add_and_get_policy(node=group, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policies[policy]['path'])

            if policies[policy]['policy']['is_mergeable']:
                # 9 - Verification if the policy is applied in chef node
                self.assertEquals(node_policy, ['libreoffice', 'gimp'])
                # 10 - Remove policy in group
                policy_applied = self.remove_policy_and_get_dotted(group, chef_node_id, GroupResource, policies[policy]['path'])

                # 11 - Verification if the OU's policy is applied in chef node
                self.assertEquals(policy_applied, ['gimp'])
            else:
                # 9 - Verification if the policy is applied in chef node
                self.assertEquals(node_policy, policies[policy]['policy_data_node_2']['shutdown_mode'])

                # 10 - Remove policy in group
                policy_applied = self.remove_policy_and_get_dotted(group, chef_node_id, GroupResource, policies[policy]['path'])

                # 11 - Verification if the OU's policy is applied in chef node
                self.assertEquals(policy_applied, 'reboot')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_09_priority_user_groups_same_ou(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                             isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 9:
        1. Check the registration work station works
        2. Check the policies priority works using groups in the same OU
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)

        # 6 - Assign A group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group_a)

        # 7 - Assign B group to user
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group_b)

        # Check if group's node is update in node chef
        group_a = db.nodes.find_one({'name': new_group_a['name']})
        self.assertEqual(group_a['members'][0], user['_id'])
        group_b = db.nodes.find_one({'name': new_group_b['name']})
        self.assertEqual(group_b['members'][0], user['_id'])

        policies = self.get_default_policies()
        for policy in policies:
            # 8 - Add policy in A group
            group_a['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
            group_a_policy = self.add_and_get_policy(node=group_a, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policies[policy]['path'])

            # 9 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEquals(group_a_policy, policies[policy]['policy_data_node_1']['package_list'])
            else:
                self.assertEquals(group_a_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

            # 10 -  Add policy in B group
            group_b['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_2']}
            group_b_policy = self.add_and_get_policy(node=group_b, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policies[policy]['path'])
            if policies[policy]['policy']['is_mergeable']:
                # 11 - Verification if the policy is applied in chef node
                self.assertEquals(group_b_policy, ['libreoffice', 'gimp'])
                # 12 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a, chef_node_id, GroupResource, policies[policy]['path'])

                # 13 - Verification if the B group's policy is applied in chef node
                self.assertEquals(policy_applied, ['libreoffice'])
            else:
                # 11 - Verification if the policy is applied in chef node
                self.assertEquals(group_b_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

                # 12 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a, chef_node_id, GroupResource, policies[policy]['path'])

                # 13 - Verification if the B group's policy is applied in chef node
                self.assertEquals(policy_applied, 'halt')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_10_priority_user_groups_different_ou(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                                  isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 10:
        1. Check the registration work station works
        2. Check the policies priority works using groups in differents OUs
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)

        # 6 - Assign A group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group_a)

        # 7  - Assign B group to user
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group_b)

        # Check if group's node is update in node chef
        group_a = db.nodes.find_one({'name': new_group_a['name']})
        self.assertEqual(group_a['members'][0], user['_id'])
        group_b = db.nodes.find_one({'name': new_group_b['name']})
        self.assertEqual(group_b['members'][0], user['_id'])

        policies = self.get_default_policies()
        for policy in policies:
            # 8 - Add policy in A group
            group_a['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
            group_a_policy = self.add_and_get_policy(node=group_a, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policies[policy]['path'])

            # 9 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEquals(group_a_policy, policies[policy]['policy_data_node_1']['package_list'])
            else:
                self.assertEquals(group_a_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

            # 10 -  Add policy in B group
            group_b['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_2']}
            group_b_policy = self.add_and_get_policy(node=group_b, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policies[policy]['path'])
            if policies[policy]['policy']['is_mergeable']:
                # 11 - Verification if the policy is applied in chef node
                self.assertEquals(group_b_policy, ['libreoffice', 'gimp'])
                # 12 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a, chef_node_id, GroupResource, policies[policy]['path'])

                # 13 - Verification if the B group's policy is applied in chef node
                self.assertEquals(policy_applied, ['libreoffice'])
            else:
                # 11 - Verification if the policy is applied in chef node
                self.assertEquals(group_b_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

                # 12 - Remove policy in A group
                policy_applied = self.remove_policy_and_get_dotted(group_a, chef_node_id, GroupResource, policies[policy]['path'])

                # 13 - Verification if the B group's policy is applied in chef node
                self.assertEquals(policy_applied, 'halt')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_11_move_workstation(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                 isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 11:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # 1 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 2 - Add policy in OU
        package_res_policy = self.get_default_ws_policy()
        policy_path = package_res_policy['path'] + '.package_list'
        ou_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['gimp'], 'pkgs_to_remove': []}}
        package_res_node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_path)

        # 3 - Verification if this policy is applied in chef node
        self.assertEquals(package_res_node_policy, ['gimp'])

        # 4 - Add policy in domain
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        domain_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['libreoffice'], 'pkgs_to_remove': []}}
        package_res_domain_policy = self.add_and_get_policy(node=domain_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_path)

        # 5 - Verification if the OU's policy is applied in chef node
        self.assertEquals(package_res_domain_policy, ['libreoffice', 'gimp'])

        # 6 - Move workstation to domain_1
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer, ComputerResource.schema_detail)
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
        self.assertEquals(package_list, ['libreoffice'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_12_move_user(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                          isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 12:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)

        # 4 - Add policy in OU
        user_launcher_policy = self.get_default_user_policy()
        policy_path = user_launcher_policy['path'] + '.users.' + username + '.launchers'
        ou_1['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['OUsLauncher']}}
        node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_path)

        # 5 - Verification if this policy is applied in chef node
        self.assertEquals(node_policy, ['OUsLauncher'])

        # 6 - Add policy in domain
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        domain_1['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['DomainLauncher']}}
        self.add_and_get_policy(node=domain_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_path)

        # 7 - Verification if the OU's policy is applied in chef node
        self.assertEquals(node_policy, ['OUsLauncher'])

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
        self.assertEquals(package_list, ['DomainLauncher'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_13_group_visibility(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                 isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 13:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)

        # 3 -Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group)
        user = db.nodes.find_one({'name': username})

        # 4 - Verification that the user can't be assigned to group
        self.assertEqual(user['memberof'], [])

        # 5 - Create group in Domain
        data, new_group_b = self.create_group('group_B', ou_name='Domain 1')

        # 6 - Assign group to user
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group_b)
        user = db.nodes.find_one({'name': username})

        # 7 - Verification that the user has been assigned to user successfully
        self.assertEqual(user['memberof'][0], ObjectId(new_group_b['_id']))

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_14_printer_visibility(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                   isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 14:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # 1 - Create a group in OU
        data, new_group = self.create_group('group_test')

        # Create printer in other OU
        data, new_ou = self.create_ou('OU 2')
        self.assertEqualsObjects(data, new_ou)
        data, new_printer = self.create_printer('printer test', 'OU 2')

        # Create a workstation in OU
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # Assign group to computer
        computer = db.nodes.find_one({'name': 'testing'})
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group)

        computer = db.nodes.find_one({'name': computer['name']})
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])

        # 3, 4 - Add printer to group and check if it is applied in chef node
        printer_policy = db.policies.find_one({'slug': 'printer_can_view'})
        group['policies'] = {unicode(printer_policy['_id']): {'object_related_list': [new_printer['_id']]}}
        policy_path = printer_policy['path']
        printer_policy = self.add_and_get_policy(node=group, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policy_path)
        self.assertEqual(printer_policy, [])

        # 5 - Create printer
        data, new_printer_ou = self.create_printer('printer OU')

        # 6, 7 - Add printer to group and check if it is applied in chef node
        printer_policy = db.policies.find_one({'slug': 'printer_can_view'})
        group['policies'] = {unicode(printer_policy['_id']): {'object_related_list': [new_printer_ou['_id']]}}
        policy_path = printer_policy['path']
        printer_policy = self.add_and_get_policy(node=group, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policy_path)
        self.assertEqualsObjects(printer_policy[0], new_printer_ou, fields=('oppolicy',
                                                                            'model',
                                                                            'uri',
                                                                            'name',
                                                                            'manufacturer'))

        node = NodeMock(chef_node_id, None)
        node.attributes.get_dotted(policy_path)

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_15_shared_folder_visibility(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                         isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 15:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # 1 - Create a group in OU
        data, new_group = self.create_group('group_test')

        # Create new OU
        data, new_ou = self.create_ou('OU 2')
        self.assertEqualsObjects(data, new_ou)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group)

        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], user['_id'])

        # 3, 4 - Add printer to group and check if it is applied in chef node
        storage_policy = db.policies.find_one({'slug': 'storage_can_view'})
        group['policies'] = {unicode(storage_policy['_id']): {'object_related_list': [new_storage['_id']]}}
        policy_path = storage_policy['path'] + '.' + username + '.gtkbookmarks'
        storage_policy = self.add_and_get_policy(node=group, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policy_path)
        self.assertEqual(storage_policy, [])

        # 5 - Create a storage
        data, new_storage_ou = self.create_storage('shared_folder_ou')

        # 6,7 - Add printer to group and check if it is applied in chef node
        storage_policy = db.policies.find_one({'slug': 'storage_can_view'})
        group['policies'] = {unicode(storage_policy['_id']): {'object_related_list': [new_storage_ou['_id']]}}
        storage_policy = self.add_and_get_policy(node=group, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policy_path)
        self.assertEqualsObjects(storage_policy[0], new_storage_ou, fields=('name',
                                                                            'uri'))
        node = NodeMock(chef_node_id, None)
        node.attributes.get_dotted(policy_path)

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_16_repository_visibility(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                      isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 16:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # 1 - Create a group in OU
        data, new_group = self.create_group('group_test')

        # Create new OU
        data, new_ou = self.create_ou('OU 2')
        self.assertEqualsObjects(data, new_ou)

        # 2 - Create a repository
        data, new_repository = self.create_repository('repo_ou2', new_ou['name'])

        # Create a workstation in OU
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Register user in chef node
        username = 'testuser'
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group)

        group = db.nodes.find_one({'name': 'group_test'})
        self.assertEqual(group['members'][0], user['_id'])

        # 3, 4 - Add repository to group and check if it is applied in chef node
        storage_policy = db.policies.find_one({'slug': 'repository_can_view'})
        group['policies'] = {unicode(storage_policy['_id']): {'object_related_list': [new_repository['_id']]}}
        policy_path = storage_policy['path']
        node_policy = self.add_and_get_policy(node=group, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policy_path)
        self.assertEqual(node_policy, [])

        # 5 - Create a repository
        data, new_repository_ou = self.create_repository('repo_ou')

        # 6, 7 - Add repository to group and check if it is applied in chef node
        group['policies'] = {unicode(storage_policy['_id']): {'object_related_list': [new_repository_ou['_id']]}}
        node_policy = self.add_and_get_policy(node=group, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policy_path)
        self.assertEqualsObjects(node_policy[0], new_repository_ou, fields=('key_server',
                                                                            'uri',
                                                                            'components',
                                                                            'repo_key',
                                                                            'deb_src'))
        # 8 - Create a repository
        data, new_repository_ou_2 = self.create_repository('repo_ou_mergeable')

        # 9, 10 - Add repository to group and check if it is applied in chef node
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        ou_1['policies'] = {unicode(storage_policy['_id']): {'object_related_list': [new_repository_ou_2['_id']]}}
        node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_path)

        self.assertEmitterObjects(node_policy, [new_repository_ou, new_repository_ou_2], fields=('key_server',
                                                                                                 'uri',
                                                                                                 'components',
                                                                                                 'repo_key',
                                                                                                 'deb_src'))

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_17_delete_ou_with_workstation_and_user_in_domain(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
                                                              gettext, create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 17:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock,
                         create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass)

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 1 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 2 - Create user in domain
        username = 'usertest'
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        data, new_user = self.create_user(username, domain_1['name'])

        # 3 - Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})

        # 4 - Verification that the user has been registered successfully
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Delete OU
        self.delete_node(ou_1, OrganisationalUnitResource)
        self.assertDeleted(field_name='name', field_value=ou_1['name'])

        # 6, 7 - Verification that the OU and worskstation have been deleted successfully
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
    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_18_delete_ou_with_user_and_workstation_in_domain(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
                                                              gettext, create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 18:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock,
                         create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Add policy in user and check if this policy is applied in chef node
        user_launcher_policy = self.get_default_user_policy()
        policy_path = user_launcher_policy['path'] + '.users.' + username + '.launchers'
        user_policy = db.nodes.find_one({'name': username})
        user_policy['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['UserLauncher']}}
        user_policy = self.add_and_get_policy(node=user_policy, chef_node_id=chef_node_id, api_class=UserResource, policy_path=policy_path)
        self.assertEquals(user_policy, ['UserLauncher'])

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
    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_19_delete_ou_with_group(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                     isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass,
                                     TaskNodeClass, TaskClientClass):
        '''
        Test 19:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock,
                         create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Assign group to computer
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group)
        computer = db.nodes.find_one({'name': computer['name']})

        # 6 - Verification if the group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])

        # 7 - Delete OU
        self.delete_node(ou_1, OrganisationalUnitResource)
        self.assertDeleted(field_name='name', field_value='OU 1')

        # 8, 9 - Verification if the OU, workstation, group and user have been deleted successfully
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
    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_20_delete_group_with_workstation_and_user(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
                                                       gettext, create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 20:
        1. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock,
                         create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Assign group to computer
        computer = db.nodes.find_one({'name': computer['name']})
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group)

        # 6 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group)

        # 7 - Check if group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])
        self.assertEqual(group['members'][1], user['_id'])

        # 8 - Delete group
        self.delete_node(group, GroupResource)
        self.assertDeleted(field_name='name', field_value=new_group['name'])

        # 9 - Verification if the groups has been deleted successfully from chef node, user and workstation.
        user = db.nodes.find_one({'name': username})
        group = db.nodes.find_one({'name': new_group['name']})
        workstation = db.nodes.find_one({'name': computer['name']})
        self.assertIsNone(group)
        self.assertEqual(workstation['memberof'], [])
        self.assertEqual(user['memberof'], [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_21_delete_group_with_politic(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext,
                                          create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 21:
        1. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock,
                         create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Assign group to computer
        computer = db.nodes.find_one({'name': computer['name']})
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group)

        # 6 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])
        self.assertEqual(group['members'][1], user['_id'])

        # 7, 8 - Add policy in Group and check if this policy is applied in chef node
        group_launcher_policy = self.get_default_user_policy()
        policy_path = group_launcher_policy['path'] + '.users.' + username + '.launchers'
        group['policies'] = {unicode(group_launcher_policy['_id']): {'launchers': ['OUsLauncher']}}
        node_policy = self.add_and_get_policy(node=group, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policy_path)
        self.assertEquals(node_policy, ['OUsLauncher'])

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
    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_22_delete_group_in_domain_with_politic(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
                                                    gettext, create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 22:
        1. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock,
                         create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Assign group to computer
        computer = db.nodes.find_one({'name': computer['name']})
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group)

        # 6 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])
        self.assertEqual(group['members'][1], user['_id'])

        # 7, 8 - Add policy in Group and check if this policy is applied in chef node
        group_launcher_policy = self.get_default_user_policy()
        policy_path = group_launcher_policy['path'] + '.users.' + username + '.launchers'
        group['policies'] = {unicode(group_launcher_policy['_id']): {'launchers': ['OUsLauncher']}}
        node_policy = self.add_and_get_policy(node=group, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policy_path)
        self.assertEquals(node_policy, ['OUsLauncher'])

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
    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_23_delete_group_in_domain_with_workstation_and_user(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
                                                                 gettext, create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 23:
        1. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock,
                         create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Assign group to computer
        computer = db.nodes.find_one({'name': computer['name']})
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group)

        # 6 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group)

        # 7 - Check if group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])
        self.assertEqual(group['members'][1], user['_id'])

        # 8 - Delete group
        request = self.dummy_get_request(group, GroupResource.schema_detail)
        group_api = GroupResource(request)
        group = group_api.get()
        self.delete_node(group, GroupResource)

        # 9 - Verification that the group has been delete from chef node, user and workstation
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
    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_24_delete_OU_without_group_inside(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext,
                                               create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 24:
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock,
                         create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 5 - Assign group to computer
        computer = db.nodes.find_one({'name': computer['name']})
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group)

        # 6 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group)

        # 7 - Check if group's node is update in node chef
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'][0], computer['_id'])
        self.assertEqual(group['members'][1], user['_id'])

        # 8 - Delete ou
        ou = db.nodes.find_one({'name': 'OU 1'})
        self.delete_node(ou, OrganisationalUnitResource)
        self.assertDeleted(field_name='name', field_value=ou['name'])

        # 10 - Verification if the user and computer have been disassociate from group
        group = db.nodes.find_one({'name': new_group['name']})
        self.assertEqual(group['members'], [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_25_priority_grouped_ous_workstation(self, get_cookbook_method, get_cookbook_method_tasks,
                                                 NodeClass, ChefNodeClass, isinstance_method):
        '''
        Test 25:
        1. Check the policies pripority works using organisational unit
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method)

        # 1 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()
        policies = self.get_default_policies()

        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        for policy in policies:
            # 2 - Add policy in OU
            ou_1['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
            node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policies[policy]['path'])

            # 3 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['package_list'])
            else:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

            # 4 - Add policy in domain
            domain_1['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_2']}
            domain_policy = self.add_and_get_policy(node=domain_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policies[policy]['path'])

            if policies[policy]['policy']['is_mergeable']:
                # 5 - Verification if OU's and Domain's policy is applied in chef node
                self.assertEquals(domain_policy, ['libreoffice', 'gimp'])
            else:
                # 5  Verification if OU's policy is applied in chef node
                self.assertEquals(domain_policy, policies[policy]['policy_data_node_1']['shutdown_mode'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_26_priority_user_and_group(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                        isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 26:
        1. Check the registration work station works
        2. Check the policies priority works using organisational unit and user
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 1 - Create user
        username = 'testuser'
        data, new_user = self.create_user(username)
        self.assertEqualsObjects(data, new_user)

        # 2- Create a group
        data, new_group = self.create_group('testgroup')

        # 3 - Register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 4 - Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)

        # 5 - Assign group to user
        user = db.nodes.find_one({'name': username})
        self.assign_group_to_node(node_name=user['name'], api_class=UserResource, group=new_group)

        policies = self.get_default_policies_user()
        group = db.nodes.find_one({'name': 'testgroup'})
        user = db.nodes.find_one({'name': username})
        for policy in policies:
            # 6 - Add policy in group
            group['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_1']}
            name_element_policy = policies[policy]['policy_data_node_1']
            policy_path_1 = policies[policy]['path'] + username + '.' + name_element_policy.keys()[0]
            node_policy = self.add_and_get_policy(node=group, chef_node_id=chef_node_id, api_class=GroupResource, policy_path=policy_path_1)
            # 7 - Verification if this policy is applied in chef node
            if policies[policy]['policy']['is_mergeable']:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['desktops'])
            else:
                self.assertEquals(node_policy, policies[policy]['policy_data_node_1']['desktop_file'])
            # 8 - Add policy in user
            name_element_policy = policies[policy]['policy_data_node_2']
            policy_path_2 = policies[policy]['path'] + username + '.' + name_element_policy.keys()[0]
            user['policies'] = {unicode(policies[policy]['policy']['_id']): policies[policy]['policy_data_node_2']}
            node_policy = self.add_and_get_policy(node=user, chef_node_id=chef_node_id, api_class=UserResource, policy_path=policy_path_2)

            if policies[policy]['policy']['is_mergeable']:
                # 9 - Verification if this policy is applied in chef node
                self.assertEquals(node_policy, ['sublime', 'kate'])
                # 10 - Remove user's policy and verification if group's policy is applied in chef node
                policy_applied = self.remove_policy_and_get_dotted(user, chef_node_id, UserResource, policy_path_1)
                self.assertEquals(policy_applied, ['kate'])
            else:
                # 9 - Verification if this policy is applied in chef node
                self.assertEquals(node_policy, policies[policy]['policy_data_node_2']['desktop_file'])
                # 10 - Remove user's policy and verification if group's policy is applied in chef node
                policy_applied = self.remove_policy_and_get_dotted(user, chef_node_id, UserResource, policy_path_2)
                self.assertEquals(policy_applied, 'mountain.png')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_27_profile_software_policy(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
                                        gettext, create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 27:
        1. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock,
                         create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass)

        # 1 - Create a group
        data, new_group = self.create_group('testgroup', ou_name='Domain 1')

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # 1, 2 - Create and register workstation
        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Create user in OU
        username = 'usertest'
        data, new_user = self.create_user(username)

        # 4 - Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # Import profile software
        self.import_profile_software()
        painter = db.software_profiles.find_one({'name': 'painter'})
        vector = db.software_profiles.find_one({'name': 'vector'})

        # 5 - Add policy in OU
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        package_profile_res = db.policies.find_one({'slug': 'package_profile_res'})
        policy_dir = 'gecos_ws_mgmt.software_mgmt.package_profile_res.package_list'
        ou_1['policies'] = {unicode(package_profile_res['_id']): {'object_related_list': [unicode(vector['_id'])]}}
        node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_dir)

        # 6 - Verification if this policy is applied in chef node
        self.assertEquals(node_policy, [u'inkscape', u'krita'])

        # 7 - Add policy in workstation
        computer = db.nodes.find_one({'name': 'testing'})
        computer['policies'] = {unicode(package_profile_res['_id']): {'object_related_list': [unicode(painter['_id'])]}}
        node_policy = self.add_and_get_policy(node=computer, chef_node_id=chef_node_id, api_class=ComputerResource, policy_path=policy_dir)

        # 8 - Verification if this policy is applied in chef node
        self.assertItemsEqual(node_policy, [u'gimp', u'pidgin', u'inkscape', u'krita'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_28_repositories_are_mergeables(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                            isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 28:
        1. Check the repositories are mergeables
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

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

        repository_policy = db.policies.find_one({'slug': 'repository_can_view'})
        policy_path = repository_policy['path']

        # 4 - Add repository to workstation
        computer = db.nodes.find_one({'name': 'testing'})
        computer['policies'] = {unicode(repository_policy['_id']): {'object_related_list': [new_repo1['_id']]}}
        node_policy = self.add_and_get_policy(node=computer, chef_node_id=chef_node_id, api_class=ComputerResource, policy_path=policy_path)

        # 5 - Add repository 2 to OU
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        ou_1['policies'] = {unicode(repository_policy['_id']): {'object_related_list': [new_repo2['_id']]}}

        node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_path)

        # 6 - Verification if the repositories are applied to user in chef node
        self.assertEmitterObjects(node_policy, [new_repo1, new_repo2], fields=('name',
                                                                               'uri'))

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_29_cert_policy(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
                            gettext, create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 29:
        1. Check the policies priority works
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock,
                         create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass)

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
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)
        user = db.nodes.find_one({'name': username})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # 4 - Add policy in OU
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        cert_res = db.policies.find_one({'slug': 'cert_res'})
        policy_dir = 'gecos_ws_mgmt.misc_mgmt.cert_res'
        ou_1['policies'] = {unicode(cert_res['_id']): {'java_keystores': ["keystore_ou"], 'ca_root_certs': [{'name': "cert_ou", 'uri': "uri_ou"}]}}
        node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_dir)

        # 5 - Verification if this policy is applied in chef node
        self.assertEquals(node_policy.get('java_keystores'), ['keystore_ou'])
        self.assertEquals(node_policy.get('ca_root_certs'), [{u'name': u'cert_ou', u'uri': u'uri_ou'}])

        # 6 - Add policy in workstation
        computer = db.nodes.find_one({'name': 'testing'})
        computer['policies'] = {unicode(cert_res['_id']): {'java_keystores': ["keystore_ws"], 'ca_root_certs': [{'name': "cert_ws", 'uri': "uri_ws"}]}}
        node_policy = self.add_and_get_policy(node=computer, chef_node_id=chef_node_id, api_class=ComputerResource, policy_path=policy_dir)

        # 7 - Verification if this policy is applied in chef node
        self.assertEquals(node_policy.get('java_keystores'), ['keystore_ou', 'keystore_ws'])
        self.assertEquals(node_policy.get('ca_root_certs'), [{u'name': u'cert_ou', u'uri': u'uri_ou'}, {u'name': u'cert_ws', u'uri': u'uri_ws'}])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_30_recalc_command_cert_policy(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method,
                                           gettext, create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):

        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock,
                         create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass)

        # 1 - 7
        self.test_29_cert_policy()

        node = NodeMock(CHEF_NODE_ID, None)

        # 8 - Modify the data in chef node
        policy_path = 'gecos_ws_mgmt.misc_mgmt.cert_res.ca_root_certs'
        node.attributes.set_dotted(policy_path, [{u'name': u'cert_ou_fake', u'uri': u'uri_ou'}, {u'name': u'cert_ws', u'uri': u'uri_ws_fake'}])
        node.save()

        # 9 - Check if the data has beed modified in chef node
        node_policy = node.attributes.get_dotted(policy_path)
        self.assertEquals(node_policy, [{u'name': u'cert_ou_fake', u'uri': u'uri_ou'}, {u'name': u'cert_ws', u'uri': u'uri_ws_fake'}])

        # 10 - Runs recalc command
        self.recalc_policies()

        # 11 - Check if the data applied in chef node is correct
        node_policy = node.attributes.get_dotted(policy_path)
        self.assertEquals(node_policy, [{u'name': u'cert_ou', u'uri': u'uri_ou'}, {u'name': u'cert_ws', u'uri': u'uri_ws'}])

        self.assertNoErrorJobs()


class MovementsTests(BaseGecosTestCase):

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_01_printers_movements(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                   isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 01:
        1. Check the printers movements work
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # 1 - Create printer
        data, new_printer = self.create_printer('Testprinter')

        # 2 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Add printer to workstation and check if it is applied in chef node
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer, ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()

        printer_policy = db.policies.find_one({'slug': 'printer_can_view'})
        computer['policies'] = {unicode(printer_policy['_id']): {'object_related_list': [new_printer['_id']]}}
        policy_path = printer_policy['path']
        self.add_and_get_policy(node=computer, chef_node_id=chef_node_id, api_class=ComputerResource, policy_path=policy_path)

        printer = db.nodes.find_one({'name': 'Testprinter'})
        # 4 - Move printer to the OU path
        try:
            printer_update = self.update_node(obj=new_printer, field_name='path',
                                              field_value=ou_1['path'], api_class=PrinterResource,
                                              is_superuser=False)
        except HTTPForbidden:
            printer_update = printer

        # 5 - Checks if the printer has been moved and check if the policy has been updated
        self.assertEqual(printer_update['path'], printer['path'])
        node = NodeMock(CHEF_NODE_ID, None)
        printer_policy = node.attributes.get_dotted(policy_path)
        self.assertEqualsObjects(printer_policy[0], new_printer, fields=('oppolicy',
                                                                         'model',
                                                                         'uri',
                                                                         'name',
                                                                         'manufacturer'))
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
                                          field_value=ou_2['path'] + ',' + unicode(ou_2['_id']),
                                          api_class=PrinterResource,
                                          is_superuser=True)

        # 10 - Check if the printer is moved and the policy has been updated
        self.assertNotEqual(printer_update['path'], printer['path'])
        node = NodeMock(CHEF_NODE_ID, None)
        printer_policy = node.attributes.get_dotted(policy_path)
        self.assertEquals(printer_policy, [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_02_shared_folder_movements(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                        isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 02:
        1. Check the shared folder movements work
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

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
        self.assertEqualsObjects(data, new_user)

        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 4 - Register user in ws
        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)

        # 5 - Add storage to user and check if it is applied in chef node
        user = db.nodes.find_one({'name': username})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        storage_policy = db.policies.find_one({'slug': 'storage_can_view'})

        user['policies'] = {unicode(storage_policy['_id']): {'object_related_list': [new_storage['_id']]}}
        policy_path = storage_policy['path'] + '.' + username + '.gtkbookmarks'
        self.add_and_get_policy(node=user, chef_node_id=chef_node_id, api_class=UserResource, policy_path=policy_path)

        storage = db.nodes.find_one({'name': 'shared folder'})
        # 6 - Move storage
        try:
            storage_update = self.update_node(obj=new_storage, field_name='path',
                                              field_value=ou_2['path'], api_class=StorageResource,
                                              is_superuser=False)
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
        self.assertEqualsObjects(printer_policy[0], storage, fields=('oppolicy',
                                                                     'model',
                                                                     'uri',
                                                                     'name',
                                                                     'manufacturer'))
        # 10 - Create another OU
        data, ou_3 = self.create_ou('OU 3')

        # 11 - Move storage in the OU 3 like admin
        storage_update = self.update_node(obj=new_storage, field_name='path',
                                          field_value=ou_3['path'] + ',' + ou_3['_id'], api_class=StorageResource,
                                          is_superuser=True)

        # 12 - Check if the storage is moved and the policy has been updated
        self.assertNotEqual(storage_update['path'], storage['path'])
        node = NodeMock(CHEF_NODE_ID, None)
        try:
            printer_policy = node.attributes.get_dotted(policy_path)
            self.assertEquals(printer_policy, [])
        except KeyError:
            self.assertEquals([], [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_03_repository_movements(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                     isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 03:
        1. Check the repository movements work
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # 1 - Create printer
        data, new_repository = self.create_repository('Testrepo')

        # 2 - Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        chef_node_id = CHEF_NODE_ID
        self.register_computer()

        # 3 - Add repository to workstation
        repository_policy = db.policies.find_one({'slug': 'repository_can_view'})
        policy_path = repository_policy['path']
        computer = db.nodes.find_one({'name': 'testing'})
        computer['policies'] = {unicode(repository_policy['_id']): {'object_related_list': [new_repository['_id']]}}
        self.add_and_get_policy(node=computer, chef_node_id=chef_node_id, api_class=ComputerResource, policy_path=policy_path)

        repository = db.nodes.find_one({'name': 'Testrepo'})
        # 4 - Move repository to the OU path
        try:
            repository_update = self.update_node(obj=new_repository, field_name='path',
                                                 field_value=ou_1['path'], api_class=RepositoryResource,
                                                 is_superuser=False)
        except HTTPForbidden:
            repository_update = repository
        # 5 - Checks if the repository has been moved
        self.assertEqual(repository_update['path'], repository['path'])

        # 6 - Move repository to the OU path like admin
        repository_update = self.update_node(obj=new_repository, field_name='path',
                                             field_value=ou_1['path'], api_class=RepositoryResource,
                                             is_superuser=True)

        # 7 - Checks if the repository has been moved
        self.assertNotEqual(repository_update['path'], repository['path'])

        # 8 - Create another OU
        data, ou_2 = self.create_ou('OU 2')

        # 9 - Move printer to OU 2 like superadmin
        repository = db.nodes.find_one({'name': 'Testrepo'})
        repository_path = repository['path']
        repository_update = self.update_node(obj=repository, field_name='path',
                                             field_value=ou_2['path'] + ',' + unicode(ou_2['_id']),
                                             api_class=RepositoryResource,
                                             is_superuser=True)

        # 10 - Check if the printer is moved and the policy has been updated
        self.assertNotEqual(repository_update['path'], repository_path)
        node = NodeMock(CHEF_NODE_ID, None)
        printer_policy = node.attributes.get_dotted(policy_path)
        self.assertEquals(printer_policy, [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_04_groups_movements(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                 isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 04:
        1. Check the groups movements work
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # 1- Create a group
        data, new_group = self.create_group('testgroup')

        # 2 - Register a workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        self.register_computer()
        computer = db.nodes.find_one({'name': 'testing'})

        # 3 - Assign group to computer
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': 'testgroup'})
        self.assertEqual(group['members'][0], computer['_id'])

        # 4 - move group to the OU path
        try:
            group_update = self.update_node(obj=group, field_name='path',
                                            field_value=ou_1['path'], api_class=GroupResource,
                                            is_superuser=False)
        except HTTPForbidden:
            group_update = group

        # 5 - Check if the groups has been moved
        self.assertEqual(group_update['path'], group['path'])

        # 6 - move group to the OU path like admin
        group = db.nodes.find_one({'name': 'testgroup'})
        group_path = group['path']
        group_update = self.update_node(obj=group, field_name='path',
                                        field_value=ou_1['path'], api_class=GroupResource,
                                        is_superuser=True)
        # 7 - Check if the groups has been moved
        self.assertNotEqual(group_update['path'], group_path)
        self.assertNotEqual(group_update['members'], [])

        # 8 - Create another OU
        data, ou_2 = self.create_ou('OU 2')

        # 9 - Move group to OU 2 like superadmin
        group = db.nodes.find_one({'name': 'testgroup'})
        group_path = group['path']
        group_update = self.update_node(obj=group, field_name='path',
                                        field_value=ou_2['path'] + ',' + unicode(ou_2['_id']),
                                        api_class=GroupResource,
                                        is_superuser=True)

        # 10 - Check if the group is moved and the policy has been updated
        self.assertNotEqual(group_update['path'], group_path)
        self.assertEqual(group_update['members'], [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_05_groups_movements_domain(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                        isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 05:
        1. Check the groups movements work
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # 1- Create a group
        data, new_group = self.create_group('testgroup')

        # 2 - Register a workstation
        db = self.get_db()
        self.register_computer()
        computer = db.nodes.find_one({'name': 'testing'})

        # 3 - Assign group to computer
        self.assign_group_to_node(node_name=computer['name'], api_class=ComputerResource, group=new_group)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': 'testgroup'})
        self.assertEqual(group['members'][0], computer['_id'])

        # 4 - Create domain
        data = {'name': 'Flag',
                'type': 'ou',
                'path': 'root',
                'source': 'gecos'}

        request_post = self.get_dummy_json_post_request(data, OrganisationalUnitResource.schema_detail)
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

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_06_OUs_movements(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                              isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 06:
        1. Check the ous movements work
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

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

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_07_OUs_movements_domain(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                     isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 07:
        1. Check the ous movements work
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)

        # 1 - Create domain
        data = {'name': 'Flag',
                'type': 'ou',
                'path': 'root',
                'source': 'gecos'}

        request_post = self.get_dummy_json_post_request(data, OrganisationalUnitResource.schema_detail)
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
                                        field_value=domain['path'], api_class=OrganisationalUnitResource,
                                        is_superuser=True)
        except HTTPForbidden:
            ou_moved = ou_1

        # 9- Check if the storage has been moved
        self.assertEqual(ou_moved['path'], ou_1['path'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_08_complete_policy(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass,
                                isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 08:
        1. Check the ous movements work
        '''
        self.apply_mocks(get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext_mock, create_chef_admin_user_method, ChefNodeStatusClass)
        chef_node_id = CHEF_NODE_ID

        # 1 - Create OU 1
        data, ou_1 = self.create_ou('OU 1')

        # 2 - Create OU 2
        data, ou_2 = self.create_ou('OU 2')

        # 3 - Create OU 3
        data, ou_3 = self.create_ou('OU 3', 'OU 1')

        # 4 - Create user, workstation, storage and 5 - Assign user to computer
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        username = 'testuser'
        data, user = self.create_user(username, 'OU 3')
        self.assertEqualsObjects(data, user)

        db = self.get_db()
        chef_node_id = CHEF_NODE_ID
        self.register_computer(ou_name=ou_3['name'])

        self.assign_user_to_node(gcc_superusername=admin_username, chef_node_id=chef_node_id, username=username)

        data, storage = self.create_storage('shared folder', ou_3['name'])
        data, storage_ou_1 = self.create_storage('shared folder_ou_1', ou_1['name'])

        user = db.nodes.find_one({'name': username})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        storage_policy = db.policies.find_one({'slug': 'storage_can_view'})

        user['policies'] = {unicode(storage_policy['_id']): {'object_related_list': [storage['_id']]}}
        storage_policy_path = storage_policy['path'] + '.' + username + '.gtkbookmarks'
        node_policy = self.add_and_get_policy(node=user, chef_node_id=chef_node_id, api_class=UserResource, policy_path=storage_policy_path)

        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        ou_1['policies'] = {unicode(storage_policy['_id']): {'object_related_list': [storage_ou_1['_id']]}}
        node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=storage_policy_path)

        # 7 - add package policy to OU_1, OU_3 and ws
        package_res_policy = self.get_default_ws_policy()
        policy_path = package_res_policy['path'] + '.package_list'
        ou_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['gimp'], 'pkgs_to_remove': []}}
        package_res_node_policy = self.add_and_get_policy(node=ou_1, chef_node_id=chef_node_id, api_class=OrganisationalUnitResource, policy_path=policy_path)

        apply_package = [{'node': 'testing', 'api_type': ComputerResource, 'package': 'sublime'},
                         {'node': 'OU 1', 'api_type': OrganisationalUnitResource, 'package': 'gimp'},
                         {'node': 'OU 3', 'api_type': OrganisationalUnitResource, 'package': 'kate'}]

        package_res_policy = self.get_default_ws_policy()
        policy_path = package_res_policy['path'] + '.package_list'

        for node in apply_package:
            node_to_apply = db.nodes.find_one({'name': node['node']})
            node_to_apply['policies'] = {unicode(package_res_policy['_id']): {'package_list': [node['package']], 'pkgs_to_remove': []}}
            package_res_node_policy = self.add_and_get_policy(node=node_to_apply, chef_node_id=chef_node_id, api_class=node['api_type'], policy_path=policy_path)

        self.assertItemsEqual(package_res_node_policy, [u'kate', u'sublime', u'gimp'])
        self.assertEmitterObjects(node_policy, [storage_ou_1, storage], fields=('name',
                                                                                'uri'))

        # 8 - Move OU 3 to OU 1 path
        ou_3 = db.nodes.find_one({'name': 'OU 3'})
        self.update_node(obj=ou_3, field_name='path',
                         field_value=ou_1['path'], api_class=OrganisationalUnitResource,
                         is_superuser=True)

        # 9 - Check if the policies has been updated in chef node
        node = NodeMock(chef_node_id, None)
        node_storage_policy = node.attributes.get_dotted(storage_policy_path)
        node_package_policy = node.attributes.get_dotted(policy_path)

        self.assertEmitterObjects(node_storage_policy, [storage], fields=('name',
                                                                          'uri'))
        self.assertItemsEqual(node_package_policy, [u'kate', u'sublime'])

        self.assertNoErrorJobs()
