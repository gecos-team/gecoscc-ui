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
        if key in self.data:
            return self.data[key]
        return default

    def set_dotted(self, key, value):
        data = self.data
        key_splitted = key.split('.')
        for k in key_splitted[:-1]:
            if k not in data:
                data[k] = {}
            data = data[k]
        data[key_splitted[-1]] = value

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
            NODES[self.name] = copy(self.attributes.data)

    def get(self, key, default=None):
        return self.attributes.get(key, default)

    def save(self):
        NODES[self.name] = self.attributes.data

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
        Useful method, returns a typical put request
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

    def assertNoErrorJobs(self):
        '''
        Useful method, check there are not any job with error (or even success)
        every job should be "processing"
        '''
        db = self.get_db()
        self.assertEqual(db.jobs.find({'status': {'$ne': 'processing'}}).count(),
                         0)

    def assertEqualsObjects(self, data, new_data, schema_data=None, schema_new_data=None):
        '''
        Useful method, check the second dictionary has the same values than
        the first. The second dictionary could have other attrs
        '''
        if schema_data:
            data = schema_data().serialize(data)
        if schema_new_data:
            new_data = schema_new_data().serialize(new_data)
        for field_name, field_value in data.items():
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

    def create_user(self, username, api_class):
        '''
        Useful method, create an User
        '''
        data = {'name': username,
                'email': '%s@example.com' % username,
                'type': 'user',
                'source': 'gecos'}
        return self.create_node(data, api_class)

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

    def update_node(self, obj, field_name, field_value, api_class):
        '''
        Useful method, update a node
        '''
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

    def register_a_computer(self, data):
        request = self.get_dummy_request()
        request.POST = data
        computer_response = RegisterComputerResource(request)
        response = computer_response.post()
        self.assertEqual(response['ok'], True)

    def add_admin_user(self, username):
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
        user_response = ChefStatusResource(request)
        response_user = user_response.put()
        self.assertEqual(response_user['ok'], True)

    def add_policy(self, node, node_id, api_class, policy_dir=None):
        request_put = self.get_dummy_json_put_request(node, api_class.schema_detail)
        node_api = api_class(request_put)
        node_update = node_api.put()
        self.assertEqualsObjects(node, node_update, api_class.schema_detail)
        node = NodeMock(node_id, None)
        if policy_dir is not None:
            launchers = node.attributes.get_dotted('gecos_ws_mgmt.' + policy_dir)
            return launchers


class BasicTests(BaseGecosTestCase):

    def test_1_home(self):
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
    def test_2_printers(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 2: Create, update and delete a printer
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        request = self.get_dummy_request()
        printer_api = PrinterResource(request)
        self.assertIsPaginatedCollection(data=printer_api.collection_get())

        data = {'connection': 'network',
                'manufacturer': 'Calcomp',
                'model': 'Artisan 1023 penplotter',
                'name': 'Printer tests',
                'oppolicy': 'default',
                'printtype': 'laser',
                'source': 'gecos',
                'type': 'printer',
                'uri': 'http://test.example.com'}

        data, new_printer = self.create_node(data, PrinterResource)
        self.assertEqualsObjects(data, new_printer)

        printer_updated = self.update_node(obj=new_printer, field_name='description',
                                           field_value=u'Test', api_class=PrinterResource)
        self.assertEqualsObjects(new_printer, printer_updated, PrinterResource.schema_detail)

        self.delete_node(printer_updated, PrinterResource)
        self.assertDeleted(field_name='name', field_value='Printer tests')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_3_shared_folder(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 3: Create, update and delete a shared folder
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        request = self.get_dummy_request()
        folder_api = StorageResource(request)
        self.assertIsPaginatedCollection(data=folder_api.collection_get())

        data = {'name': 'Folder',
                'type': 'storage',
                'source': 'gecos',
                'uri': 'http://test.folder.com'}

        data, new_folder = self.create_node(data, StorageResource)
        self.assertEqualsObjects(data, new_folder)

        folder_updated = self.update_node(obj=new_folder, field_name='uri', field_value=u'Test',
                                          api_class=StorageResource)
        self.assertEqualsObjects(new_folder, folder_updated, StorageResource.schema_detail)

        self.delete_node(folder_updated, StorageResource)
        self.assertDeleted(field_name='name', field_value='Folder tests')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_4_repository(self, get_cookbook_method, get_cookbook_method_tasks):
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
    def test_5_user(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 5: Create, update and delete an user
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        request = self.get_dummy_request()
        user_api = UserResource(request)
        self.assertIsPaginatedCollection(data=user_api.collection_get())

        data, new_user = self.create_user('adiaz', UserResource)
        self.assertEqualsObjects(data, new_user)

        user_updated = self.update_node(obj=new_user, field_name='first_name',
                                        field_value=u'Another name', api_class=UserResource)
        self.assertEqualsObjects(new_user, user_updated, UserResource.schema_detail)

        self.delete_node(user_updated, UserResource)
        self.assertDeleted(field_name='first_name', field_value='Another name')

        self.assertNoErrorJobs()

    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_6_group(self, get_cookbook_method, get_cookbook_method_tasks):
        '''
        Test 6: Creation and delete a group
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        request = self.get_dummy_request()
        group_api = GroupResource(request)
        self.assertIsPaginatedCollection(data=group_api.collection_get())

        data = {'name': 'Group',
                'type': 'group',
                'source': 'gecos'}
        data, new_group = self.create_node(data, GroupResource)
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
    def test_7_computer(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, TaskNodeClass, ClientClass, isinstance_method):
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

        request = self.get_dummy_request()
        request.POST = data
        computer_response = RegisterComputerResource(request)

        response = computer_response.post()
        self.assertEqual(response['ok'], True)
        self.assertNoErrorJobs()

        computer_api = ComputerResource(request)
        computer = computer_api.collection_get()

        computer_updated = self.update_node(obj=computer['nodes'][0], field_name='family',
                                            field_value=u'laptop', api_class=ComputerResource)
        self.assertEqualsObjects(computer['nodes'][0], computer_updated, ComputerResource.schema_detail)

        self.delete_node(computer_updated, ComputerResource)
        self.assertDeleted(field_name='name', field_value='testing')

        self.assertNoErrorJobs()


class AdvancedTests(BaseGecosTestCase):

    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_1_priority_ous_workstation(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method):
        '''
        Test 1:
        1. Check the registration work station works
        2. Check the policies pripority works (with organisational unit)
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
        self.register_a_computer(data)

        # Add policy in OU and check if this policy is applied in chef node
        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        ou_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['gimp'], 'pkgs_to_remove': []}}
        launchers = self.add_policy(node=ou_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir='software_mgmt.package_res.package_list')
        self.assertEquals(launchers, ['gimp'])

        # Add policy in domain and check if this policy is applied in chef node
        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        domain_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['libreoffice'], 'pkgs_to_remove': []}}
        launchers = self.add_policy(node=domain_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir='software_mgmt.package_res.package_list')
        self.assertEquals(launchers, ['gimp'])

        # Remove policy in OU and check if this policy is applied in chef node
        ou_1['policies'] = {}
        request_put = self.get_dummy_json_put_request(ou_1, OrganisationalUnitResource.schema_detail)
        ou_api = OrganisationalUnitResource(request_put)
        ou_1_updated = ou_api.put()
        self.assertEqualsObjects(ou_1, ou_1_updated, OrganisationalUnitResource.schema_detail)
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted('gecos_ws_mgmt.software_mgmt.package_res.package_list')
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
    def test_2_priority_user_workstation(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method, gettext, create_chef_admin_user_method, ChefNodeStatusClass):
        '''
        Test 2:
        1. Check the registration work station works
        2. Check the policies pripority works (with organisational unit and user)
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
        data, new_user = self.create_user('testuser', UserResource)
        self.assertEqualsObjects(data, new_user)

        # Register workstation
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})
        node_id = '36e13492663860e631f53a00afcdd92d'
        data = {'ou_id': ou_1['_id'],
                'node_id': node_id}
        self.register_a_computer(data)

        # Register user in chef node
        self.assign_user_to_node(gcc_superusername=admin_username, node_id=node_id, username='testuser')

        # Add policy in OU and check if this policy is applied in chef node
        user_launcher_policy = db.policies.find_one({'slug': 'user_launchers_res'})
        ou_1['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['OUsLauncher']}}
        launchers = self.add_policy(node=ou_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir='users_mgmt.user_launchers_res.users.testuser.launchers')
        self.assertEquals(launchers, ['OUsLauncher'])

        # Add policy in user and check if this policy is applied in chef node
        user_policy = db.nodes.find_one({'name': 'testuser'})
        user_policy['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['UserLauncher']}}
        launchers = self.add_policy(node=user_policy, node_id=node_id, api_class=UserResource, policy_dir='users_mgmt.user_launchers_res.users.testuser.launchers')
        self.assertEquals(launchers, ['UserLauncher'])

        # Remove policy in OU and check if this policy is applied in chef node
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
        user_policy['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['UserLauncherWithoutComputer']}}
        launchers = self.add_policy(node=user_policy, node_id=node_id, api_class=UserResource, policy_dir='users_mgmt.user_launchers_res.users.usertest.launchers')
        self.assertEquals(launchers, ['UserLauncherWithoutComputer'])

        # Add policy in OU and check if this policy is applied in chef node
        user_launcher_policy = db.policies.find_one({'slug': 'user_launchers_res'})
        ou_1['policies'] = {unicode(user_launcher_policy['_id']): {'launchers': ['OUsLauncher']}}
        launchers = self.add_policy(node=ou_1, node_id=node_id, api_class=OrganisationalUnitResource, policy_dir='users_mgmt.user_launchers_res.users.usertest.launchers')
        self.assertEquals(launchers, ['UserLauncherWithoutComputer'])

        self.assertNoErrorJobs()
