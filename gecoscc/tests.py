#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
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
from gecoscc.db import get_db
from gecoscc.userdb import get_userdb
from gecoscc.permissions import LoggedFactory, SuperUserFactory
from gecoscc.views.portal import home
from gecoscc.views.admins import admin_add

# This url is not used, every time the code should use it, the code is patched
# and the code use de NodeMock class
CHEF_URL = 'https://CHEF_URL/'


def create_chef_admin_user_mock(api, settings, username, password=None):
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

    def __init__(self, node_id, api):
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

    def __init__(self, node_id, api):
        super(NodeMock, self).__init__()
        self.name = node_id
        node_default_json = open('gecoscc/test_resources/node_default.json').read().replace(
            '%(chef_url)s', CHEF_URL).replace('%s(node_name)s', node_id)
        self.default = NodeAttributesMock(json.loads(node_default_json), self, 'default')

        if node_id in NODES:
            self.attributes = NodeAttributesMock(copy(NODES[node_id]), self)
            self.normal = self.attributes
        else:
            node_attributes_json = open('gecoscc/test_resources/node_attributes.json').read().replace(
                '%(chef_url)s', CHEF_URL).replace('%s(node_name)s', node_id)
            self.attributes = NodeAttributesMock(json.loads(node_attributes_json), self)
            self.normal = self.attributes

    def get(self, key, default=None):
        return self.attributes.get(key, default)

    def save(self):
        NODES[self.name] = copy(self.attributes.data)

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

    def get_dummy_request(self):
        '''
        Useful method, returns a typical request, with the same request properties
        than pyramid add (see gecoscc/__init__)
        '''
        request = testing.DummyRequest()
        request.db = get_db(request)
        request.userdb = get_userdb(request)
        user = request.db.adminusers.find_one({'is_superuser': True})
        if not user:
            user = request.userdb.create_user('test', 'test', 'test@example.com', {'is_superuser': True})
        request.user = request.db.adminusers.find_one({'is_superuser': True})
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

    def get_dummy_json_put_request(self, data, schema=None):
        '''
        Useful method, returns a typical put request
        '''
        request = self.get_dummy_request()
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
        printer_deleted = self.get_db().nodes.find_one({field_name: field_value})
        self.assertIsNone(printer_deleted)

    def assertIsPaginatedCollection(self, data):
        '''
        Useful method. check if data is a paginated collection
        '''
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

        data = {'name': 'Domain 1',
                'type': 'ou',
                'path': '%s,%s' % (flag_new['path'], flag_new['_id']),
                'master': 'gecos',
                'source': 'gecos'}

        request_post = self.get_dummy_json_post_request(data, OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request_post)
        domain_new = ou_api.collection_post()

        data = {'name': 'OU 1',
                'type': 'ou',
                'path': '%s,%s' % (domain_new['path'], domain_new['_id']),
                'source': 'gecos'}

        request_post = self.get_dummy_json_post_request(data, OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request_post)
        domain_new = ou_api.collection_post()

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

    def create_group(self, group_name, ou_name='OU 1'):
        '''
        Useful method, create a group
        '''

        data = {'name': group_name,
                'type': 'group',
                'source': 'gecos'}

        return self.create_node(data, GroupResource, ou_name)

    def create_printer(self, printer_name):
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
        return self.create_node(data, PrinterResource)

    def create_storage(self, storage_name):
        '''
        Useful method, create a Storage
        '''
        data = {'name': storage_name,
                'type': 'storage',
                'source': 'gecos',
                'uri': 'http://%s.storage.com' % storage_name}
        return self.create_node(data, StorageResource)

    def create_user(self, username, ou_name='OU 1'):
        '''
        Useful method, create an User
        '''
        data = {'name': username,
                'email': '%s@example.com' % username,
                'type': 'user',
                'source': 'gecos'}
        return self.create_node(data, UserResource, ou_name)

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
        return self.create_node(data, OrganisationalUnitResource, ou_name='Domain 1')

    def update_node(self, obj, field_name, field_value, api_class):
        '''
        Useful method, update a node
        '''
        if isinstance(obj[field_name], list):
            obj[field_name].append(field_value)
        else:
            obj[field_name] = field_value
        request_put = self.get_dummy_json_put_request(obj, api_class.schema_detail)
        api = api_class(request_put)
        return api.put()

    def delete_node(self, obj, api_class):
        '''
        Useful method, delete a node
        '''
        request_delete = self.get_dummy_delete_request(obj, api_class.schema_detail)
        api = api_class(request_delete)
        return api.delete()

    def register_computer(self, data):
        '''
        Useful method, register a computer
        '''
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

    def assign_user_to_node(self, gcc_superusername, node_id, username):
        '''
        Useful method, assign an user to a node
        '''
        node = NodeMock(node_id, None)
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

    def add_and_get_policy(self, node, node_id, api_class, policy_dir=None):
        '''
        Useful method, add policy to node and return this policy
        '''
        request_put = self.get_dummy_json_put_request(node, api_class.schema_detail)
        node_api = api_class(request_put)
        node_update = node_api.put()
        self.assertEqualsObjects(node, node_update, api_class.schema_detail)

        node = NodeMock(node_id, None)
        if policy_dir is not None:
            node_policy = node.attributes.get_dotted(policy_dir)
            return node_policy


class BasicTests(BaseGecosTestCase):

    def test_01_home(self):
        '''
        Test 1: Check the home works
        '''
        request = self.get_dummy_request()
        context = LoggedFactory(request)
        response = home(context, request)
        self.assertEqual(json.loads(response['websockets_enabled']), False)
        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_02_printers(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 2: Create, update and delete a printer
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        request = self.get_dummy_request()
        printer_api = PrinterResource(request)
        self.assertIsPaginatedCollection(data=printer_api.collection_get())

        data, new_printer = self.create_printer('Testprinter')
        self.assertEqualsObjects(data, new_printer)

        printer_updated = self.update_node(obj=new_printer, field_name='description',
                                           field_value=u'Test', api_class=PrinterResource)
        self.assertEqualsObjects(new_printer, printer_updated, PrinterResource.schema_detail)

        self.delete_node(printer_updated, PrinterResource)
        self.assertDeleted(field_name='name', field_value='Printer tests')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_03_shared_folder(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 3: Create, update and delete a shared folder
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        request = self.get_dummy_request()
        folder_api = StorageResource(request)
        self.assertIsPaginatedCollection(data=folder_api.collection_get())

        data, new_folder = self.create_storage('test_storage')
        self.assertEqualsObjects(data, new_folder)

        folder_updated = self.update_node(obj=new_folder, field_name='uri', field_value=u'Test',
                                          api_class=StorageResource)
        self.assertEqualsObjects(new_folder, folder_updated, StorageResource.schema_detail)

        self.delete_node(folder_updated, StorageResource)
        self.assertDeleted(field_name='name', field_value='Folder tests')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_04_repository(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 4: Create, update and delete a repository
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        request = self.get_dummy_request()
        repository_api = RepositoryResource(request)
        self.assertIsPaginatedCollection(data=repository_api.collection_get())

        data = {'name': 'Repo',
                'repo_key': 'CJAER23',
                'key_server': 'keyring.repository.com',
                'type': 'repository',
                'source': 'gecos',
                'uri': 'http://test.repository.com'}

        data, new_repository = self.create_node(data, RepositoryResource)
        self.assertEqualsObjects(data, new_repository)

        repository_update = self.update_node(obj=new_repository, field_name='uri',
                                             field_value=u'Test', api_class=RepositoryResource)
        self.assertEqualsObjects(new_repository, repository_update, RepositoryResource.schema_detail)

        self.delete_node(repository_update, RepositoryResource)
        self.assertDeleted(field_name='name', field_value='Repo')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_05_user(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 5: Create, update and delete an user
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        data, new_user = self.create_user('adiaz')
        self.assertEqualsObjects(data, new_user)

        user_updated = self.update_node(obj=new_user, field_name='first_name',
                                        field_value=u'Another name', api_class=UserResource)
        self.assertEqualsObjects(new_user, user_updated, UserResource.schema_detail)

        self.delete_node(user_updated, UserResource)
        self.assertDeleted(field_name='first_name', field_value='Another name')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_06_group(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 6: Creation and delete a group
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        request = self.get_dummy_request()
        group_api = GroupResource(request)
        self.assertIsPaginatedCollection(data=group_api.collection_get())

        data, new_group = self.create_group('testgroup')
        self.assertEqualsObjects(data, new_group)

        self.delete_node(new_group, GroupResource)
        self.assertDeleted(field_name='name', field_value='group')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('gecoscc.tasks.Client')
    @mock.patch('gecoscc.tasks.Node')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_07_computer(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, TaskNodeClass, ClientClass, isinstance_method):
        '''
        Test 7: Create, update and delete a computer
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        TaskNodeClass.side_effect = NodeMock
        ClientClass.side_effect = ClientMock
        isinstance_method.side_effect = isinstance_mock
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}

        self.register_computer(data)

        request = self.get_dummy_request()
        computer_api = ComputerResource(request)
        computer = computer_api.collection_get()

        computer_updated = self.update_node(obj=computer['nodes'][0], field_name='family',
                                            field_value=u'laptop', api_class=ComputerResource)
        self.assertEqualsObjects(computer['nodes'][0], computer_updated, ComputerResource.schema_detail)

        self.delete_node(computer_updated, ComputerResource)
        self.assertDeleted(field_name='name', field_value='testing')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_08_OU(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 8: Create, update and delete a OU
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        request = self.get_dummy_request()
        folder_api = StorageResource(request)
        self.assertIsPaginatedCollection(data=folder_api.collection_get())

        data, new_ou = self.create_ou('OU 2')
        self.assertEqualsObjects(data, new_ou)

        ou_updated = self.update_node(obj=new_ou,
                                      field_name='extra',
                                      field_value=u'Test',
                                      api_class=OrganisationalUnitResource)
        self.assertEqualsObjects(new_ou, ou_updated, OrganisationalUnitResource.schema_detail)

        self.delete_node(ou_updated, OrganisationalUnitResource)
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
    def test_01_update_resources_user(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 1:
        1. Check the shared_folder policy works using users
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock

        # Create a storage
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        data, new_storage = self.create_storage('carpeta')

        # Register workstation
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Register admin
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='usertest')
        # Add storage to user and check if it is applied in chef node
        user = db.nodes.find_one({'name': 'usertest'})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        storage_policy = db.policies.find_one({'slug': 'storage_can_view'})

        user['policies'] = {unicode(storage_policy['_id']): {'object_related_list': [new_storage['_id']]}}
        policy_dir = storage_policy['path'] + '.usertest.gtkbookmarks'
        storage_policy = self.add_and_get_policy(node=user, node_id=node_id, api_class=UserResource, policy_dir=policy_dir)
        self.assertEqualsObjects(storage_policy[0], new_storage, fields=('name',
                                                                         'uri'))
        # Modify storage and check if is applied in chef node
        storage_update = self.update_node(obj=new_storage, field_name='uri',
                                          field_value='http://modify.storage.com', api_class=StorageResource)
        node = NodeMock(node_id, None)
        storage_policy = node.attributes.get_dotted(policy_dir)
        self.assertEqualsObjects(storage_policy[0], storage_update, fields=('name',
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
    def test_02_update_resources_workstation(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 2:
        1. Check the printer policy works using workstation
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock

        # Create printer
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        data, new_printer = self.create_printer('printer test')

        # Register workstation
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer, ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()

        # Add printer to workstation and check if it is applied in chef node
        printer_policy = db.policies.find_one({'slug': 'printer_can_view'})
        computer['policies'] = {unicode(printer_policy['_id']): {'object_related_list': [new_printer['_id']]}}
        policy_dir = printer_policy['path']
        printer_policy = self.add_and_get_policy(node=computer, node_id=node_id, api_class=ComputerResource, policy_dir=policy_dir)
        self.assertEqualsObjects(printer_policy[0], new_printer, fields=('oppolicy',
                                                                         'model',
                                                                         'uri',
                                                                         'name',
                                                                         'manufacturer'))

        # Modify printer and check if is applied in chef node
        node = NodeMock(node_id, None)
        printer_update = self.update_node(obj=new_printer, field_name='uri',
                                          field_value='http://modifiy.example.com', api_class=PrinterResource)
        printer_policy = node.attributes.get_dotted(policy_dir)
        self.assertEqualsObjects(printer_policy[0], printer_update, fields=('oppolicy',
                                                                            'model',
                                                                            'uri',
                                                                            'name',
                                                                            'manufacturer'))

        # Delete printer and check if it appears in chef node
        self.delete_node(printer_update, PrinterResource)
        self.assertDeleted(field_name='name', field_value='printer test')
        printer_policy = node.attributes.get_dotted(policy_dir)
        self.assertEqual(printer_policy, [])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_03_priority_ous_workstation(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method):
        '''
        Test 3:
        1. Check the registration work station works
        2. Check the policies pripority works using organisational unit
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock

        # Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Add policy in OU and check if this policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        policy_dir = package_res_policy['path'] + '.package_list'
        ou_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['gimp'], 'pkgs_to_remove': []}}
        package_res_ou_policy = self.add_and_get_policy(node=ou_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir=policy_dir)
        self.assertEquals(package_res_ou_policy, ['gimp'])

        # Add policy in domain and check if OU's policy is applied in chef node
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        domain_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['libreoffice'], 'pkgs_to_remove': []}}
        package_res_domain_policy = self.add_and_get_policy(node=domain_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir=policy_dir)
        self.assertEquals(package_res_domain_policy, ['gimp'])

        # Remove policy in OU and check if domain_1's policy is applied in chef node
        ou_1['policies'] = {}
        request_put = self.get_dummy_json_put_request(ou_1, OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request_put)
        ou_1_updated = ou_api.put()
        self.assertEqualsObjects(ou_1, ou_1_updated, OrganisationalUnitResource.schema_detail)
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted(policy_dir)
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
    def test_04_priority_user_workstation(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 4:
        1. Check the registration work station works
        2. Check the policies priority works using organisational unit and user
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock

        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Create a node user
        data, new_user = self.create_user('testuser')
        self.assertEqualsObjects(data, new_user)

        # Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='testuser')

        # Add policy in OU and check if this policy is applied in chef node
        user_launcher_policy = db.policies.find_one({'slug': 'user_launchers_res'})
        policy_dir = user_launcher_policy['path'] + '.users.testuser.launchers'
        ou_1['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['OUsLauncher']}}
        ou_policy = self.add_and_get_policy(node=ou_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir=policy_dir)
        self.assertEquals(ou_policy, ['OUsLauncher'])

        # Add policy in user and check if this policy is applied in chef node
        user_policy = db.nodes.find_one({'name': 'testuser'})
        user_policy['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['UserLauncher']}}
        user_policy = self.add_and_get_policy(node=user_policy, node_id=node_id, api_class=UserResource, policy_dir=policy_dir)
        self.assertEquals(user_policy, ['UserLauncher'])

        # Remove policy in OU
        user_launcher_policy = db.policies.find_one({'slug': 'user_launchers_res'})
        ou_1['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': []}}
        request_put = self.get_dummy_json_put_request(ou_1, OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request_put)
        ou_1_updated = ou_api.put()
        self.assertEqualsObjects(ou_1, ou_1_updated, OrganisationalUnitResource.schema_detail)

        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='usertest')

        # Add policy in user and check if this policy is applied in chef node
        user_policy = db.nodes.find_one({'name': 'usertest'})
        policy_dir = user_launcher_policy['path'] + '.users.usertest.launchers'
        user_policy['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['UserLauncherWithoutComputer']}}
        user_policy = self.add_and_get_policy(node=user_policy, node_id=node_id, api_class=UserResource, policy_dir=policy_dir)
        self.assertEquals(user_policy, ['UserLauncherWithoutComputer'])

        # Add policy in OU and check if the user's policy is applied in chef node
        user_launcher_policy = db.policies.find_one({'slug': 'user_launchers_res'})
        ou_1['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['OUsLauncher']}}
        ou_policy = self.add_and_get_policy(node=ou_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir=policy_dir)
        self.assertEquals(ou_policy, ['UserLauncherWithoutComputer'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_05_priority_workstation_ous_groups(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 5:
        1. Check the registration work station works
        2. Check the policies priority works using organisational unit and groups
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock

        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Create a group
        data, new_group = self.create_group('testgroup')

        # Create a workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Assign group to computer
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer, ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()

        id_group = new_group['_id']
        id_group = ObjectId(id_group)

        self.update_node(obj=computer,
                         field_name='memberof',
                         field_value=id_group,
                         api_class=ComputerResource)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': 'testgroup'})
        self.assertEqual(group['members'][0], computer['_id'])

        # Add policy in OU and check if this policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        policy_dir = package_res_policy['path'] + '.package_list'
        ou_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['gimp'], 'pkgs_to_remove': []}}
        package_res_ou_policy = self.add_and_get_policy(node=ou_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir=policy_dir)
        self.assertEquals(package_res_ou_policy, ['gimp'])

        # Add policy in Group and check if this policy is applied in chef node
        policy_dir = package_res_policy['path'] + '.package_list'
        group['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['libreoffice'], 'pkgs_to_remove': []}}
        package_res_ou_policy = self.add_and_get_policy(node=group, node_id=node_id, api_class=GroupResource, policy_dir=policy_dir)
        self.assertEquals(package_res_ou_policy, ['libreoffice'])

        # Remove policy in Group and check if the OU's policy is applied in chef node
        group['policies'] = {}
        request_put = self.get_dummy_json_put_request(group, GroupResource.schema_detail)
        group_api = GroupResource(request_put)
        group_updated = group_api.put()
        self.assertEqualsObjects(group, group_updated, GroupResource.schema_detail)
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted(policy_dir)
        self.assertEquals(package_list, ['gimp'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_06_priority_workstation_groups(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 6:
        1. Check the registration work station works
        2. Check the policies priority works using workstation and groups
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock

        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Create a group
        data, new_group_a = self.create_group('group_A')

        # Create a group
        data, new_group_b = self.create_group('group_B')

        # Create a workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Assign groupA and groupB to computer
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer, ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()

        id_group_a = new_group_a['_id']
        id_group_a = ObjectId(id_group_a)

        self.update_node(obj=computer,
                         field_name='memberof',
                         field_value=id_group_a,
                         api_class=ComputerResource)

        id_group_b = new_group_b['_id']
        id_group_b = ObjectId(id_group_b)
        self.update_node(obj=computer,
                         field_name='memberof',
                         field_value=id_group_b,
                         api_class=ComputerResource)

        # Check if group's node is update in node chef
        group_a = db.nodes.find_one({'name': 'group_A'})
        self.assertEqual(group_a['members'][0], computer['_id'])
        group_b = db.nodes.find_one({'name': 'group_B'})
        self.assertEqual(group_b['members'][0], computer['_id'])

        # Add policy in A group and check if this policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        policy_dir = package_res_policy['path'] + '.package_list'
        group_a['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['libreoffice'], 'pkgs_to_remove': []}}
        package_res_group_policy = self.add_and_get_policy(node=group_a, node_id=node_id, api_class=GroupResource, policy_dir=policy_dir)
        self.assertEquals(package_res_group_policy, ['libreoffice'])

        # Add policy in B group and check if the A group's policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        policy_dir = package_res_policy['path'] + '.package_list'
        group_b['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['gimp'], 'pkgs_to_remove': []}}
        package_res_group_policy = self.add_and_get_policy(node=group_b, node_id=node_id, api_class=GroupResource, policy_dir=policy_dir)
        self.assertEquals(package_res_group_policy, ['libreoffice'])

        # Remove policy in A group and check if the B group's policy is applied in chef node
        group_a['policies'] = {}
        request_put = self.get_dummy_json_put_request(group_a, GroupResource.schema_detail)
        group_api = GroupResource(request_put)
        group_updated = group_api.put()
        self.assertEqualsObjects(group_a, group_updated, GroupResource.schema_detail)
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted(policy_dir)
        self.assertEquals(package_list, ['gimp'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_07_priority_workstation_groups_different_ou(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 7:
        1. Check the registration work station works
        2. Check the policies priority works using groups in differents OUs
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock

        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Create a group
        data, new_group_a = self.create_group('group_A')

        # Create a group
        data, new_group_b = self.create_group('group_B', ou_name='Domain 1')

        # Create a workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Assign groupA and groupB to computer
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer, ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()

        id_group_a = new_group_a['_id']
        id_group_a = ObjectId(id_group_a)

        self.update_node(obj=computer,
                                           field_name='memberof',
                                           field_value=id_group_a,
                                           api_class=ComputerResource)

        id_group_b = new_group_b['_id']
        id_group_b = ObjectId(id_group_b)
        self.update_node(obj=computer,
                         field_name='memberof',
                         field_value=id_group_b,
                         api_class=ComputerResource)

        # Check if group's node is update in node chef
        group_a = db.nodes.find_one({'name': 'group_A'})
        self.assertEqual(group_a['members'][0], computer['_id'])
        group_b = db.nodes.find_one({'name': 'group_B'})
        self.assertEqual(group_b['members'][0], computer['_id'])

        # Add policy in A group and check if this policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        policy_dir = package_res_policy['path'] + '.package_list'
        group_a['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['libreoffice'], 'pkgs_to_remove': []}}
        package_res_group_policy = self.add_and_get_policy(node=group_a, node_id=node_id, api_class=GroupResource, policy_dir=policy_dir)
        self.assertEquals(package_res_group_policy, ['libreoffice'])

        # Add policy in B group and check if the A group's policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        policy_dir = package_res_policy['path'] + '.package_list'
        group_b['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['gimp'], 'pkgs_to_remove': []}}
        package_res_group_policy = self.add_and_get_policy(node=group_b, node_id=node_id, api_class=GroupResource, policy_dir=policy_dir)
        self.assertEquals(package_res_group_policy, ['libreoffice'])

        # Remove policy in A group and check if the B group's policy is applied in chef node
        group_a['policies'] = {}
        request_put = self.get_dummy_json_put_request(group_a, GroupResource.schema_detail)
        group_api = GroupResource(request_put)
        group_updated = group_api.put()
        self.assertEqualsObjects(group_a, group_updated, GroupResource.schema_detail)
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted(policy_dir)
        self.assertEquals(package_list, ['gimp'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_08_priority_user_ous_groups(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 8:
        1. Check the registration work station works
        2. Check the policies priority works using groups and OUs
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock

        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Create a group
        data, new_group = self.create_group('group_test')

        # Create a workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='testuser')

        # Assign group to user
        user = db.nodes.find_one({'name': 'testuser'})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_user = new_group['_id']
        id_user = ObjectId(id_user)
        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        self.update_node(obj=user,
                         field_name='memberof',
                         field_value=id_user,
                         api_class=UserResource)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': 'group_test'})
        self.assertEqual(group['members'][0], user['_id'])

        # Add policy in OU and check if this policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        policy_dir = package_res_policy['path'] + '.package_list'
        ou_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['libreoffice'], 'pkgs_to_remove': []}}
        package_res_ou_policy = self.add_and_get_policy(node=ou_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir=policy_dir)
        self.assertEquals(package_res_ou_policy, ['libreoffice'])

        # Add policy in group and check if this policy is applied in chef node
        policy_dir = package_res_policy['path'] + '.package_list'
        group['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['gimp'], 'pkgs_to_remove': []}}
        package_res_group_policy = self.add_and_get_policy(node=group, node_id=node_id, api_class=GroupResource, policy_dir=policy_dir)
        self.assertEquals(package_res_group_policy, ['gimp'])

        # Remove policy in group and check if the OU's policy is applied in chef node
        group['policies'] = {}
        request_put = self.get_dummy_json_put_request(group, GroupResource.schema_detail)
        group_api = GroupResource(request_put)
        group_updated = group_api.put()
        self.assertEqualsObjects(group, group_updated, GroupResource.schema_detail)
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted(policy_dir)
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
    def test_09_priority_user_groups_same_ou(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 9:
        1. Check the registration work station works
        2. Check the policies priority works using groups in the same OU
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock

        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Create a group
        data, new_group_a = self.create_group('group_A')

        # Create a group
        data, new_group_b = self.create_group('group_B', ou_name='Domain 1')

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='testuser')

        # Assign A group and B group to user
        user = db.nodes.find_one({'name': 'testuser'})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_user = new_group_a['_id']
        id_user = ObjectId(id_user)
        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        self.update_node(obj=user,
                         field_name='memberof',
                         field_value=id_user,
                         api_class=UserResource)

        id_user = new_group_b['_id']
        id_user = ObjectId(id_user)
        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        self.update_node(obj=user,
                         field_name='memberof',
                         field_value=id_user,
                         api_class=UserResource)

        # Check if group's node is update in node chef
        group_a = db.nodes.find_one({'name': 'group_A'})
        self.assertEqual(group_a['members'][0], user['_id'])
        group_b = db.nodes.find_one({'name': 'group_B'})
        self.assertEqual(group_b['members'][0], user['_id'])

        # Add policy in A group and check if this policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        policy_dir = package_res_policy['path'] + '.package_list'
        group_a['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['libreoffice'], 'pkgs_to_remove': []}}
        package_res_group_policy = self.add_and_get_policy(node=group_a, node_id=node_id, api_class=GroupResource, policy_dir=policy_dir)
        self.assertEquals(package_res_group_policy, ['libreoffice'])

        # Add policy in B group and check if the A group's policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        policy_dir = package_res_policy['path'] + '.package_list'
        group_b['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['gimp'], 'pkgs_to_remove': []}}
        package_res_group_policy = self.add_and_get_policy(node=group_b, node_id=node_id, api_class=GroupResource, policy_dir=policy_dir)
        self.assertEquals(package_res_group_policy, ['libreoffice'])

        # Remove policy in A group and check if the B group's policy is applied in chef node
        group_a['policies'] = {}
        request_put = self.get_dummy_json_put_request(group_a, GroupResource.schema_detail)
        group_api = GroupResource(request_put)
        group_updated = group_api.put()
        self.assertEqualsObjects(group_a, group_updated, GroupResource.schema_detail)
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted(policy_dir)
        self.assertEquals(package_list, ['gimp'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_10_priority_user_groups_different_ou(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 10:
        1. Check the registration work station works
        2. Check the policies priority works using groups in differents OUs
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock

        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Create a group
        data, new_group_a = self.create_group('group_A')

        # Create a group
        data, new_group_b = self.create_group('group_B', ou_name='Domain 1')

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='testuser')

        # Assign A group and B group to user
        user = db.nodes.find_one({'name': 'testuser'})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_user = new_group_a['_id']
        id_user = ObjectId(id_user)
        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        self.update_node(obj=user,
                         field_name='memberof',
                         field_value=id_user,
                         api_class=UserResource)

        id_user = new_group_b['_id']
        id_user = ObjectId(id_user)
        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        self.update_node(obj=user,
                         field_name='memberof',
                         field_value=id_user,
                         api_class=UserResource)

        # Check if group's node is update in node chef
        group_a = db.nodes.find_one({'name': 'group_A'})
        self.assertEqual(group_a['members'][0], user['_id'])
        group_b = db.nodes.find_one({'name': 'group_B'})
        self.assertEqual(group_b['members'][0], user['_id'])

        # Add policy in A group and check if this policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        policy_dir = package_res_policy['path'] + '.package_list'
        group_a['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['libreoffice'], 'pkgs_to_remove': []}}
        package_res_group_policy = self.add_and_get_policy(node=group_a, node_id=node_id, api_class=GroupResource, policy_dir=policy_dir)
        self.assertEquals(package_res_group_policy, ['libreoffice'])

        # Add policy in B group and check if the A group's policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        policy_dir = package_res_policy['path'] + '.package_list'
        group_b['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['gimp'], 'pkgs_to_remove': []}}
        package_res_group_policy = self.add_and_get_policy(node=group_b, node_id=node_id, api_class=GroupResource, policy_dir=policy_dir)
        self.assertEquals(package_res_group_policy, ['libreoffice'])

        # Remove policy in A group and check if the B group's policy is applied in chef node
        group_a['policies'] = {}
        request_put = self.get_dummy_json_put_request(group_a, GroupResource.schema_detail)
        group_api = GroupResource(request_put)
        group_updated = group_api.put()
        self.assertEqualsObjects(group_a, group_updated, GroupResource.schema_detail)
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted(policy_dir)
        self.assertEquals(package_list, ['gimp'])

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.api.chef_status.Node')
    @mock.patch('gecoscc.forms.create_chef_admin_user')
    @mock.patch('gecoscc.forms._')
    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_11_move_workstation(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 11:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock

        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Add policy in OU and check if this policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        policy_dir = package_res_policy['path'] + '.package_list'
        ou_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['gimp'], 'pkgs_to_remove': []}}
        package_res_ou_policy = self.add_and_get_policy(node=ou_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir=policy_dir)
        self.assertEquals(package_res_ou_policy, ['gimp'])

        # Add policy in domain and check if the OU's policy is applied in chef node
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        domain_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['libreoffice'], 'pkgs_to_remove': []}}
        package_res_domain_policy = self.add_and_get_policy(node=domain_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir=policy_dir)

        self.assertEquals(package_res_domain_policy, ['gimp'])

        # Move workstation to domain_1
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer, ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()
        self.assertNoErrorJobs()
        self.update_node(obj=computer,
                         field_name='path',
                         field_value=ou_1['path'],
                         api_class=ComputerResource)

        # check if domain_1's policy is applied in chef node
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted(policy_dir)
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
    def test_12_move_user(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 12:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock

        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='testuser')

        # Add policy in OU and check if this policy is applied in chef node
        user_launcher_policy = db.policies.find_one({'slug': 'user_launchers_res'})
        policy_dir = user_launcher_policy['path'] + '.users.testuser.launchers'
        ou_1['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['OUsLauncher']}}
        ou_policy = self.add_and_get_policy(node=ou_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir=policy_dir)
        self.assertEquals(ou_policy, ['OUsLauncher'])

        # Add policy in domain and check if the OU's policy is applied in chef node
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        domain_1['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['DomainLauncher']}}
        self.add_and_get_policy(node=domain_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir=policy_dir)
        self.assertEquals(ou_policy, ['OUsLauncher'])

        # Move user to domain_1
        user = db.nodes.find_one({'name': 'testuser'})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]

        self.update_node(obj=user,
                         field_name='path',
                         field_value=ou_1['path'],
                         api_class=UserResource)

        # check if domain_1's policy is applied in chef node
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted(policy_dir)
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
    def _test_13_group_visibility(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 13:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock

        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Create a group in OU
        data, new_group = self.create_group('group_test')

        # Create a workstation in Domain
        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': domain_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)
        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='testuser')

        # Assign group to user
        user = db.nodes.find_one({'name': 'testuser'})
        request = self.dummy_get_request(user, UserResource.schema_detail)
        user_api = UserResource(request)
        user = user_api.get()

        id_user = new_group['_id']
        id_user = ObjectId(id_user)
        id_computer = user['computers']
        user['computers'] = [ObjectId(id_computer[0])]
        self.update_node(obj=user,
                         field_name='memberof',
                         field_value=id_user,
                         api_class=UserResource)

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
    def test_17_delete_ou_with_user_workstation(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 17:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock
        TaskNodeClass.side_effect = NodeMock
        TaskClientClass.side_effect = ClientMock
        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='testuser')
        user = db.nodes.find_one({'name': 'testuser'})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # Delete OU
        request = self.dummy_get_request(ou_1, OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request)
        ou_1 = ou_api.get()
        self.delete_node(ou_1, OrganisationalUnitResource)
        self.assertDeleted(field_name='extra', field_value='Test')
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        user = db.nodes.find_one({'name': 'testuser'})
        computer = db.nodes.find_one({'name': 'testing'})

        self.assertIsNone(ou_1)
        self.assertIsNone(user)
        self.assertIsNone(computer)
        self.assertIsNone(NODES)

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
    def test_18_delete_ou_with_workstation_and_user_in_domain(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 18:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock
        TaskNodeClass.side_effect = NodeMock
        TaskClientClass.side_effect = ClientMock
        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Create user in domain
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        data, new_user = self.create_user('piglesias', domain_1['name'])

        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='piglesias')
        user = db.nodes.find_one({'name': 'piglesias'})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # Delete OU
        request = self.dummy_get_request(ou_1, OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request)
        ou_1 = ou_api.get()
        self.delete_node(ou_1, OrganisationalUnitResource)
        self.assertDeleted(field_name='extra', field_value='Test')

        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertIsNone(ou_1)
        self.assertIsNone(computer)

        user = db.nodes.find_one({'name': 'piglesias'})
        self.assertIsNone(NODES)
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
    def test_19_delete_ou_with_user_and_workstation_in_domain(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 19:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock
        TaskNodeClass.side_effect = NodeMock
        TaskClientClass.side_effect = ClientMock
        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Create a workstation in Domain
        db = self.get_db()
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': domain_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Create user in OU
        data, new_user = self.create_user('piglesias')

        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='piglesias')
        user = db.nodes.find_one({'name': 'piglesias'})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # Add policy in user and check if this policy is applied in chef node
        user_launcher_policy = db.policies.find_one({'slug': 'user_launchers_res'})
        policy_dir = user_launcher_policy['path'] + '.users.piglesias.launchers'
        user_policy = db.nodes.find_one({'name': 'piglesias'})
        user_policy['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['UserLauncher']}}
        user_policy = self.add_and_get_policy(node=user_policy, node_id=node_id, api_class=UserResource, policy_dir=policy_dir)
        self.assertEquals(user_policy, ['UserLauncher'])

        # Delete OU
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        request = self.dummy_get_request(ou_1, OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request)
        ou_1 = ou_api.get()
        self.delete_node(ou_1, OrganisationalUnitResource)
        self.assertDeleted(field_name='extra', field_value='Test')

        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        user = db.nodes.find_one({'name': 'piglesias'})
        self.assertIsNone(ou_1)
        self.assertIsNone(user)

        node = NodeMock(node_id, None)
        try:
            package_list = node.attributes.get_dotted(policy_dir)
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
    def test_20_delete_ou_with_group(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass, TaskNodeClass, TaskClientClass):
        '''
        Test 20:
        1. Check the registration work station works
        2. Check the policies priority works
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
        ChefNodeStatusClass.side_effect = NodeMock
        isinstance_method.side_effect = isinstance_mock
        gettext.side_effect = gettext_mock
        create_chef_admin_user_method.side_effect = create_chef_admin_user_mock
        TaskNodeClass.side_effect = NodeMock
        TaskClientClass.side_effect = ClientMock
        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        # Create a group
        data, new_group = self.create_group('testgroup')

        # Register administrator
        admin_username = 'superuser'
        self.add_admin_user(admin_username)

        # Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_computer(data)

        # Create user in OU
        data, new_user = self.create_user('piglesias')

        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='piglesias')
        user = db.nodes.find_one({'name': 'piglesias'})
        computer = db.nodes.find_one({'name': 'testing'})
        self.assertEqual(user['computers'][0], computer['_id'])

        # Assign group to computer
        computer = db.nodes.find_one({'name': 'testing'})
        request = self.dummy_get_request(computer, ComputerResource.schema_detail)
        computer_api = ComputerResource(request)
        computer = computer_api.get()

        id_group = new_group['_id']
        id_group = ObjectId(id_group)

        self.update_node(obj=computer,
                         field_name='memberof',
                         field_value=id_group,
                         api_class=ComputerResource)

        # Check if group's node is update in node chef
        group = db.nodes.find_one({'name': 'testgroup'})
        self.assertEqual(group['members'][0], computer['_id'])

        # Delete OU
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        request = self.dummy_get_request(ou_1, OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request)
        ou_1 = ou_api.get()
        self.delete_node(ou_1, OrganisationalUnitResource)
        self.assertDeleted(field_name='extra', field_value='Test')

        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        user = db.nodes.find_one({'name': 'piglesias'})
        group = db.nodes.find_one({'name': 'testgroup'})
        workstation = db.nodes.find_one({'name': 'testing'})
        self.assertIsNone(ou_1)
        self.assertIsNone(user)
        self.assertIsNone(group)
        self.assertIsNone(workstation)
        self.assertIsNone(NODES)

        self.assertNoErrorJobs()
