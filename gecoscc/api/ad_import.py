# -*- coding: utf-8 -*-
"""
Copyright (c) 2013 Junta de Andalucia <http://www.juntadeandalucia.es> Licensed under the EUPL V.1.1
"""

import logging
import re

from ordereddict import OrderedDict
from gzip import GzipFile
from xml.dom import minidom
from StringIO import StringIO

from bson import ObjectId
from chef import Node
from chef import Client
from cornice.resource import resource
from pyramid.threadlocal import get_current_registry

from gecoscc.api import BaseAPI
from gecoscc.permissions import http_basic_login_required
from gecoscc.utils import get_chef_api

logger = logging.getLogger(__name__)


@resource(path='/api/ad_import/',
          description='Active Directory import',
          validators=http_basic_login_required)
class ADImport(BaseAPI):
    """
    Create or update objects from a Active Directory XML dump.

    Attributes:
      importSchema (list of Object): Import schema from AD XML dump.

    """
    RECIPE_NAME_OHAI_GECOS = 'recipe[ohai-gecos]'
    RECIPE_NAME_GECOS_WS_MGMT = 'recipe[gecos_ws_mgmt]'

    mongoCollectionName = 'nodes'
    importSchema = [
        {
            'adName': 'OrganizationalUnit',
            'mongoType': 'ou',
            'attributes': [
                {
                    'ad': 'ObjectGUID',
                    'mongo': 'adObjectGUID'
                },
                {
                    'ad': 'DistinguishedName',
                    'mongo': 'adDistinguishedName'
                },
                {
                    'ad': 'Name',
                    'mongo': 'name'
                },
                {
                    'ad': 'Description',
                    'mongo': 'extra'
                }
            ],
            'staticAttributes': []
        },
        {
            'adName': 'User',
            'mongoType': 'user',
            'attributes': [
                {
                    'ad': 'ObjectGUID',
                    'mongo': 'adObjectGUID'
                },
                {
                    'ad': 'DistinguishedName',
                    'mongo': 'adDistinguishedName'
                },
                {
                    'ad': 'Name',
                    'mongo': 'name'
                },
                {
                    'ad': 'Description',
                    'mongo': 'extra'
                },
                {
                    'ad': 'MemberOf',
                    'mongo': 'adMemberOf'
                },
                {
                    'ad': 'PrimaryGroup',
                    'mongo': 'adPrimaryGroup'
                },
                {
                    'ad': 'EmailAddress',
                    'mongo': 'adEmailAddress'
                },
                {
                    'ad': 'mail',
                    'mongo': 'email'
                },
                {
                    'ad': 'DisplayName',
                    'mongo': 'first_name'
                },
                {
                    'ad': 'OfficePhone',
                    'mongo': 'phone'
                }
            ],
            'staticAttributes': [
                {
                    'key': 'computers',
                    'value': []
                }]
        },
        {
            'adName': 'Group',
            'mongoType': 'group',
            'attributes': [
                {
                    'ad': 'ObjectGUID',
                    'mongo': 'adObjectGUID'
                },
                {
                    'ad': 'DistinguishedName',
                    'mongo': 'adDistinguishedName'
                },
                {
                    'ad': 'Name',
                    'mongo': 'name'
                },
                {
                    'ad': 'Description',
                    'mongo': 'extra'
                },
                {
                    'ad': 'MemberOf',
                    'mongo': 'adMemberOf'
                }
            ],
            'staticAttributes': [
                {
                    'key': 'members',
                    'value': []
                },
            ]
        },
        {
            'adName': 'Computer',
            'mongoType': 'computer',
            'attributes': [
                {
                    'ad': 'ObjectGUID',
                    'mongo': 'adObjectGUID'
                },
                {
                    'ad': 'DistinguishedName',
                    'mongo': 'adDistinguishedName'
                },
                {
                    'ad': 'Name',
                    'mongo': 'name'
                },
                {
                    'ad': 'Description',
                    'mongo': 'extra'
                },
                {
                    'ad': 'MemberOf',
                    'mongo': 'adMemberOf'
                },
                {
                    'ad': 'PrimaryGroup',
                    'mongo': 'adPrimaryGroup'
                }
            ],
            'staticAttributes': []
        },
        {
            'adName': 'Printer',
            'mongoType': 'printer',
            'attributes': [
                {
                    'ad': 'ObjectGUID',
                    'mongo': 'adObjectGUID'
                },
                {
                    'ad': 'DistinguishedName',
                    'mongo': 'adDistinguishedName'
                },
                {
                    'ad': 'Name',
                    'mongo': 'name'
                },
                {
                    'ad': 'Description',
                    'mongo': 'extra'
                },
                {
                    'ad': 'url',
                    'mongo': 'uri'
                },
                {
                    'ad': 'printerName',
                    'mongo': 'manufacturer'
                },
                {
                    'ad': 'driverName',
                    'mongo': 'model'
                }
            ],
            'staticAttributes': [
                {
                    'key': 'connection',
                    'value': 'network'
                },
                {
                    'key': 'ppd_uri',
                    'value': 'null'
                },
                {
                    'key': 'printtype',
                    'value': 'ink'
                }
            ]
        },
        {
            'adName': 'Volume',
            'mongoType': 'storage',
            'attributes': [
                {
                    'ad': 'ObjectGUID',
                    'mongo': 'adObjectGUID'
                },
                {
                    'ad': 'DistinguishedName',
                    'mongo': 'adDistinguishedName'
                },
                {
                    'ad': 'Name',
                    'mongo': 'name'
                },
                {
                    'ad': 'Description',
                    'mongo': 'extra'
                },
                {
                    'ad': 'uNCName',
                    'mongo': 'uri'
                }
            ],
            'staticAttributes': []
        }
    ]

    def _fixDuplicateName(self, mongoObjects, mongoType, newObj):
        """
        Fix duplicate name append an _counter to the name
        """
        contador = 0
        m = re.match(ur'^(.+)(_\d+)$', newObj['name'])
        if m:
            nombreBase = m.group(1)
        else:
            nombreBase = newObj['name']

        # Each object to import
        if mongoObjects is not None:
            for mongoObject in mongoObjects.values():
                m = re.match(ur'({0})(_\d+)?'.format(nombreBase), mongoObject['name'])
                if m and m.group(2):
                    nuevoContador = int(m.group(2)[1:]) + 1
                    if (nuevoContador > contador):
                        contador = nuevoContador
                elif m and 1 > contador:
                    contador = 1

        # Each object already in database
        collection = self.request.db[self.mongoCollectionName].find({
            'name': {
                '$regex': u'{0}(_\d+)?'.format(nombreBase)
            },
            'type': mongoType}, {
            'name': 1
        })
        for mongoObject in collection:
            m = re.match(ur'({0})(_\d+)?'.format(nombreBase), mongoObject['name'])
            if m and m.group(2):
                nuevoContador = int(m.group(2)[1:]) + 1
                if (nuevoContador > contador):
                    contador = nuevoContador
            elif m and 1 > contador:
                contador = 1

        if contador > 0:
            newObj['name'] = u'{0}_{1}'.format(nombreBase, contador)

    def _convertADObjectToMongoObject(self, rootOU, mongoObjects, objSchema, adObj):

        def update_object(self, rootOU, mongoObjects, objSchema, mongoObj, adObj):
            """
            Update an object from a collection with a GUID in common.
            """

            # Update MONGODB object with ACTIVE DIRECTORY attributes
            for attrib in objSchema['attributes']:
                if attrib['mongo'] != 'name':  # TODO: Proper update the object name
                    if adObj.hasAttribute(attrib['ad']):
                        mongoObj[attrib['mongo']] = adObj.attributes[attrib['ad']].value
                    else:
                        elements = adObj.getElementsByTagName(attrib['ad'])
                        if elements.length > 0:
                            mongoObj[attrib['mongo']] = []
                            items = elements[0].getElementsByTagName('Item')
                            for item in items:
                                mongoObj[attrib['mongo']].append(item.childNodes[0].nodeValue)
            for attrib in objSchema['staticAttributes']:
                if attrib['key'] not in mongoObj.keys():
                    mongoObj[attrib['key']] = attrib['value']

            # self._fixDuplicateName(mongoObjects, objSchema['mongoType'], mongoObj)

            return mongoObj

        def new_object(self, rootOU, mongoObjects, objSchema, adObj):
            """
            Create an object into a collection.
            """

            # Create the new MONGODB object.
            newObj = {}
            for attrib in objSchema['attributes']:
                if adObj.hasAttribute(attrib['ad']):
                    newObj[attrib['mongo']] = adObj.attributes[attrib['ad']].value
                else:
                    elements = adObj.getElementsByTagName(attrib['ad'])
                    if elements.length > 0:
                        newObj[attrib['mongo']] = []
                        items = elements[0].getElementsByTagName('Item')
                        for item in items:
                            newObj[attrib['mongo']].append(item.childNodes[0].nodeValue)
            # Add static attributes
            for attrib in objSchema['staticAttributes']:
                newObj[attrib['key']] = attrib['value']

            # Add additional attributes.
            newObj['source'] = rootOU['source']
            newObj['type'] = objSchema['mongoType']
            newObj['lock'] = 'false'
            newObj['policies'] = {}  # TODO: Get the proper policies

            self._fixDuplicateName(mongoObjects, objSchema['mongoType'], newObj)

            # Save the new object
            return newObj

        # Try to get an already exist object
        mongoObj = self.request.db[self.mongoCollectionName].find_one({'adObjectGUID': adObj.attributes['ObjectGUID'].value})
        if mongoObj is not None:
            return update_object(self, rootOU, mongoObjects, objSchema, mongoObj, adObj)
        else:
            return new_object(self, rootOU, mongoObjects, objSchema, adObj)

    def _getRootOU(self, ouSchema, xmlDomain):
        # Get already exists root OU
        rootOUID = self.request.POST['rootOU']
        rootOU = None
        if rootOUID not in [None, '', 'root']:
            filterRootOU = {
                '_id': ObjectId(rootOUID),
                'type': ouSchema['mongoType']
            }
            rootOU = self.request.db[self.mongoCollectionName].find_one(filterRootOU)
        if rootOU is None:
            filterRootOU = {
                'path': 'root',
                'type': ouSchema['mongoType']
            }
            rootOU = self.request.db[self.mongoCollectionName].find_one(filterRootOU)

        # Save changes to root OU
        newRootOU = {
            'name': xmlDomain.attributes['Name'].value,
            'extra': xmlDomain.attributes['DistinguishedName'].value,
            'source': u'ad:{0}:{1}'.format(xmlDomain.attributes['DistinguishedName'].value, xmlDomain.attributes['ObjectGUID'].value),
            'type': ouSchema['mongoType'],
            'lock': 'false',
            'policies': {},  # TODO: Get the proper policies
            'path': 'root',
            'adObjectGUID': xmlDomain.attributes['ObjectGUID'].value,
            'adDistinguishedName': xmlDomain.attributes['DistinguishedName'].value
        }
        if rootOU is None:
            self.request.db[self.mongoCollectionName].insert(newRootOU)
            return newRootOU
        else:
            for key, value in newRootOU.items():
                if key not in ['name', 'path']:  # TODO: Proper update the object name
                    rootOU[key] = value
            self.request.db[self.mongoCollectionName].update(filterRootOU, rootOU)
            return rootOU

    def _saveMongoObject(self, mongoObject):
        if '_id' not in mongoObject.keys():
            # Insert object
            return self.request.db[self.mongoCollectionName].insert(mongoObject)
        else:
            # Update object
            return self.request.db[self.mongoCollectionName].update({'adObjectGUID': mongoObject['adObjectGUID']}, mongoObject)

    def _orderByDependencesMongoObjects(self, mongoObjects, rootOU):

        # Order by size
        orderedBySize = {}
        er = re.compile(r'([^, ]+=(?:(?:\\,)|[^,])+)')
        for index, mongoObject in mongoObjects.items():
            if mongoObject['adDistinguishedName'] == rootOU['adDistinguishedName']:  # Jump root OU
                mongoObjectRoot = mongoObject
                continue
            subADDN = er.findall(mongoObject['adDistinguishedName'])
            size = len(subADDN)
            if size not in orderedBySize.keys():
                orderedBySize[size] = []
            orderedBySize[size].append(mongoObject)

        # Merge results in one dimensional dict
        mongoObjects = OrderedDict()
        mongoObjects[mongoObjectRoot['adDistinguishedName']] = mongoObjectRoot
        for size, listMongoObjects in orderedBySize.items():
            for mongoObject in listMongoObjects:
                mongoObjects[mongoObject['adDistinguishedName']] = mongoObject
        return mongoObjects

    def post(self):
        try:
            # Read GZIP data
            postedfile = self.request.POST['media'].file
            xmldata = GzipFile('', 'r', 9, StringIO(postedfile.read())).read()

            # Read XML data
            xmldoc = minidom.parseString(xmldata)

            # Get the root OU
            xmlDomain = xmldoc.getElementsByTagName('Domain')[0]
            rootOU = self._getRootOU(self.importSchema[0], xmlDomain)

            # Convert from AD objects to MongoDB objects
            mongoObjects = {}
            for objSchema in self.importSchema:
                objs = xmldoc.getElementsByTagName(objSchema['adName'])
                for adObj in objs:
                    if not adObj.hasAttribute('ObjectGUID'):
                        raise Exception('An Active Directory object must has "ObjectGUID" attrib.')
                    mongoObject = self._convertADObjectToMongoObject(rootOU, mongoObjects, objSchema, adObj)
                    mongoObjects[mongoObject['adDistinguishedName']] = mongoObject

            # Order mongoObjects by dependences
            mongoObjects[rootOU['adDistinguishedName']] = rootOU
            mongoObjects = self._orderByDependencesMongoObjects(mongoObjects, rootOU)

            # Save each MongoDB objects
            successCounter = 1  # root OU already saved
            properRootOUADDN = rootOU['adDistinguishedName']
            for index, mongoObject in mongoObjects.items():
                if index == properRootOUADDN:
                    continue
                # Get the proper path ("root,{0}._id,{1}._id,{2}._id...")
                listPath = re.findall(ur'([^, ]+=(?:(?:\\,)|[^,])+)', index)
                nodePath = ','.join(listPath[1:])

                # Find parent
                mongoObjectParent = mongoObjects[nodePath]
                mongoObjectParent = self.request.db[self.mongoCollectionName].find_one({'_id': mongoObjectParent['_id']})
                path = '{0},{1}'.format(mongoObjectParent['path'], str(mongoObjectParent['_id']))
                mongoObject['path'] = path
                # Save mongoObject
                self._saveMongoObject(mongoObject)
                successCounter += 1

            # AD Fixes
            chef_server_api = get_chef_api(get_current_registry().settings, self.request.user)
            for index, mongoObject in mongoObjects.items():
                updateMongoObject = False

                # Emails
                if mongoObject['type'] == 'user':
                    if ('email' not in mongoObject.keys() or mongoObject['email'] == '') and 'adEmailAddress' in mongoObject.keys():
                        mongoObject['email'] = mongoObject['adEmailAddress']
                    del mongoObject['adEmailAddress']
                    # Check that email are unique and not empty
                    if mongoObject['email'] == '':
                        mongoObject['email'] = u'{0}@example.com'.format(mongoObject['name'])
                    updateMongoObject = True

                # MemberOf
                if mongoObject['type'] in ['user', 'computer']:
                    if 'memberof' not in mongoObject.keys():
                        mongoObject['memberof'] = []
                    if 'adPrimaryGroup' in mongoObject.keys() and mongoObject['adPrimaryGroup']:
                        group = mongoObjects[mongoObject['adPrimaryGroup']]
                        if not mongoObject['_id'] in group['members']:
                            group['members'].append(mongoObject['_id'])
                            self._saveMongoObject(group)
                        mongoObject['memberof'].append(mongoObjects[mongoObject['adPrimaryGroup']]['_id'])
                        del mongoObject['adPrimaryGroup']
                        updateMongoObject = True
                    if 'adMemberOf' in mongoObject.keys() and mongoObject['adMemberOf']:
                        for group_id in mongoObject['adMemberOf']:
                            group = mongoObjects[group_id]
                            mongoObject['memberof'].append(mongoObjects[group_id]['_id'])
                            if not mongoObject['_id'] in group['members']:
                                group['members'].append(mongoObject['_id'])
                                self._saveMongoObject(group)
                        del mongoObject['adMemberOf']
                        updateMongoObject = True

                # Create Chef-Server Nodes
                if mongoObject['type'] == 'computer':
                    chef_server_node = Node(mongoObject['name'], api=chef_server_api)
                    ohai_gecos_in_runlist = self.RECIPE_NAME_OHAI_GECOS in chef_server_node.run_list
                    gecos_ws_mgmt_in_runlist = self.RECIPE_NAME_GECOS_WS_MGMT in chef_server_node.run_list
                    if not ohai_gecos_in_runlist and not gecos_ws_mgmt_in_runlist:
                        chef_server_node.run_list.append(self.RECIPE_NAME_OHAI_GECOS)
                        chef_server_node.run_list.append(self.RECIPE_NAME_GECOS_WS_MGMT)
                    elif not ohai_gecos_in_runlist and gecos_ws_mgmt_in_runlist:
                        chef_server_node.run_list.insert(chef_server_node.run_list.index(self.RECIPE_NAME_GECOS_WS_MGMT), self.RECIPE_NAME_OHAI_GECOS)
                    elif ohai_gecos_in_runlist and not gecos_ws_mgmt_in_runlist:
                        chef_server_node.run_list.insert(chef_server_node.run_list.index(self.RECIPE_NAME_OHAI_GECOS) + 1, self.RECIPE_NAME_GECOS_WS_MGMT)
                    chef_server_node.save()
                    chef_server_client = Client(mongoObject['name'], api=chef_server_api)
                    if not chef_server_client.exists:
                        chef_server_client.save()
                    mongoObject['node_chef_id'] = mongoObject['name']

                # Save changes
                if updateMongoObject:
                    self._saveMongoObject(mongoObject)

            # Return result
            totalCounter = len(mongoObjects)
            return {
                'status': '{0} of {1} objects imported successfully.'.format(successCounter, totalCounter),
                'ok': True if successCounter == totalCounter else False
            }
        except Exception as e:
            logging.exception(e)
            return {
                'status': u'{0}'.format(e),
                'ok': False
            }

    def get_collection(self, collection=None):
        return {}
