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

from copy import copy

from bson import ObjectId
from celery import current_app
from chef.node import NodeAttributes
from cornice.errors import Errors
from paste.deploy import loadapp
from pymongo import Connection
from pyramid import testing

from gecoscc.api.organisationalunits import OrganisationalUnitResource
from gecoscc.api.printers import PrinterResource
from gecoscc.api.register_computer import RegisterComputerResource
from gecoscc.commands.import_policies import Command as ImportPoliciesCommand
from gecoscc.db import get_db
from gecoscc.userdb import get_userdb
from gecoscc.permissions import LoggedFactory
from gecoscc.views.portal import home

# This url is not used, every time the code should use it, the code is patched
# and the code use de NodeMock class
CHEF_URL = 'https://CHEF_URL/'


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
                raise KeyError(key)
            data = data[k]
        data[key_splitted[-1]] = value

    def __getitem__(self, key):
        return NodeAttributesMock(self.data.__getitem__(key), self.node, self.node_attr_type)

    def __iter__(self):
        return self.data.__iter__()

    def __delitem__(self, key):
        return self.data.__delitem__(key)


class NodeMock(object):
    '''
    NodeMock emulates NodeAttributes <chef.node.Node>
    With this class and the previous class the chef client and chef server are emulated
    '''
    def __init__(self, node_id, api):
        super(NodeMock, self).__init__()
        self.name = node_id
        node_default_json = open('gecoscc/test_resources/node_default.json').read().replace(
            '%(chef_url)s', CHEF_URL).replace('%s(node_name)s', node_id)
        self.default = NodeAttributesMock(json.loads(node_default_json), self, 'default')

        if node_id in NODES:
            self.attributes = NodeAttributesMock(copy(NODES[node_id]), self)
        else:
            node_attributes_json = open('gecoscc/test_resources/node_attributes.json').read().replace(
                '%(chef_url)s', CHEF_URL).replace('%s(node_name)s', node_id)
            self.attributes = NodeAttributesMock(json.loads(node_attributes_json), self)
            NODES[self.name] = copy(self.attributes.data)

    def get(self, key, default=None):
        return self.attributes.get(key, default)

    def save(self):
        NODES[self.name] = self.attributes.data


class GecosTestCase(unittest.TestCase):

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
            request.validated = schema().serialize(data)
            request.validated['_id'] = ObjectId(request.validated['_id'])
        data['_id'] = unicode(data['_id'])
        request.json = json.dumps(data)
        request.path = '/api/%ss/%s/' % (data['type'], data['_id'])
        return request

    def assertNoErrorJobs(self):
        '''
        Useful method, check there are not any job with error (or even success)
        every job should be "processing"
        '''
        db = self.get_db()
        self.assertEqual(db.jobs.find({'status': {'$ne': 'processing'}}).count(),
                         0)

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

    def assertEqualsObjects(self, data, data_new):
        '''
        Useful method, check the second dictionary has the same values than
        the first. The second dictionary could have other attrs
        '''
        for field_name, field_value in data.items():
            self.assertEqual(field_value, data_new[field_name])

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
        Test 2: Check the printer creation work
        '''
        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        request = self.get_dummy_request()
        printer_api = PrinterResource(request)
        printers = printer_api.collection_get()
        self.assertIsInstance(printers['nodes'], list)
        self.assertIsInstance(printers['pages'], int)
        self.assertIsInstance(printers['pagesize'], int)
        self.assertEqual(printers['page'], 1)
        db = self.get_db()
        ou_1 = db.nodes.find_one({'name': 'OU 1'})

        data = {'connection': 'network',
                'manufacturer': 'Calcomp',
                'model': 'Artisan 1023 penplotter',
                'name': 'Printer tests',
                'oppolicy': 'default',
                'path': '%s,%s' % (ou_1['path'], ou_1['_id']),
                'printtype': 'laser',
                'source': 'gecos',
                'type': 'printer',
                'uri': 'http://test.example.com'}

        request_post = self.get_dummy_json_post_request(data, PrinterResource.schema_detail)
        printer_api = PrinterResource(request_post)
        printer_new = printer_api.collection_post()
        self.assertEqualsObjects(data, printer_new)
        self.assertNoErrorJobs()

    @mock.patch('gecoscc.utils.isinstance')
    @mock.patch('chef.Node')
    @mock.patch('gecoscc.utils.ChefNode')
    @mock.patch('gecoscc.tasks.get_cookbook')
    @mock.patch('gecoscc.utils.get_cookbook')
    def test_3_priority_ous(self, get_cookbook_method, get_cookbook_method_tasks, NodeClass, ChefNodeClass, isinstance_method):
        '''
        Test 3:
        1. Check the registration work station work
        2. Check the policies pripority works (with organisational unit)
        '''

        get_cookbook_method.side_effect = get_cookbook_mock
        get_cookbook_method_tasks.side_effect = get_cookbook_mock
        NodeClass.side_effect = NodeMock
        ChefNodeClass.side_effect = NodeMock
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

        package_res_policy = db.policies.find_one({'slug': 'package_res'})
        ou_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['gimp'], 'pkgs_to_remove': []}}
        request_put = self.get_dummy_json_put_request(ou_1, OrganisationalUnitResource.schema_detail)
        request_put.matchdict['oid'] = ou_1['_id']
        ou_api = OrganisationalUnitResource(request_put)
        ou_1_updated = ou_api.put()
        self.assertEqualsObjects(ou_1, ou_1_updated)
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted('gecos_ws_mgmt.software_mgmt.package_res.package_list')
        self.assertEquals(package_list, ['gimp'])
        self.assertNoErrorJobs()

        domain_1 = db.nodes.find_one({'name': 'Domain 1'})
        domain_1['policies'] = {unicode(package_res_policy['_id']): {'package_list': ['libreoffice'], 'pkgs_to_remove': []}}
        request_put = self.get_dummy_json_put_request(domain_1, OrganisationalUnitResource.schema_detail)
        request_put.matchdict['oid'] = domain_1['_id']
        ou_api = OrganisationalUnitResource(request_put)
        domain_1_updated = ou_api.put()
        self.assertEqualsObjects(domain_1, domain_1_updated)
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted('gecos_ws_mgmt.software_mgmt.package_res.package_list')
        self.assertEquals(package_list, ['gimp'])
        self.assertNoErrorJobs()

        ou_1['policies'] = {}
        request_put = self.get_dummy_json_put_request(ou_1, OrganisationalUnitResource.schema_detail)
        request_put.matchdict['oid'] = ou_1['_id']
        ou_api = OrganisationalUnitResource(request_put)
        ou_1_updated = ou_api.put()
        self.assertEqualsObjects(ou_1, ou_1_updated)
        node = NodeMock(node_id, None)
        package_list = node.attributes.get_dotted('gecos_ws_mgmt.software_mgmt.package_res.package_list')
        self.assertEquals(package_list, ['libreoffice'])
        self.assertNoErrorJobs()
