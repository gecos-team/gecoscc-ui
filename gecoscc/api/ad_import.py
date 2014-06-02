# -*- coding: utf-8 -*-
"""
Copyright (c) 2013 Junta de Andalucia <http://www.juntadeandalucia.es> Licensed under the EUPL V.1.1
"""

import re
import logging

from gzip import GzipFile
from xml.dom import minidom
from StringIO import StringIO

from cornice.resource import resource
from pyramid.httpexceptions import HTTPInternalServerError

from gecoscc.api import BaseAPI
from gecoscc.permissions import http_basic_login_required

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
                }
            ],
            'staticAttributes': []
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
                }
            ],
            'staticAttributes': []
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
                }
            ],
            'staticAttributes': []
        }
    ]

    def _fixDuplicateName(self, mongoObjects, objSchema, newObj):
        """
        Fix duplicate name append an _counter to the name
        """
        contador = 0;
        m = re.match(ur'^(.+)(_\d+)$', newObj['name'])
        if m:
            nombreBase = m.group(1)
        else:
            nombreBase = newObj['name']

        for mongoObject in mongoObjects:
            m = re.match(ur'({0})(_\d+)?'.format(nombreBase), mongoObject['name'])
            if m and m.group(2):
                nuevoContador = int(m.group(2)[1:]) + 1
                if (nuevoContador > contador):
                    contador = nuevoContador
            elif m and 1 > contador:
                contador = 1

        collection = self.request.db[self.mongoCollectionName].find({
            'name': {
                '$regex': u'{0}(_\d+)?'.format(nombreBase)
            },
            'type': objSchema['mongoType']}, {
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
                if attrib['mongo'] != 'name' and adObj.hasAttribute(attrib['ad']): #TODO: Proper update the object name
                    mongoObj[attrib['mongo']] = adObj.attributes[attrib['ad']].value

            # self._fixDuplicateName(mongoObjects, objSchema, mongoObj)

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
            # Add static attributes
            for attrib in objSchema['staticAttributes']:
                newObj[attrib['key']] = attrib['value']

            # Add additional attributes.
            newObj['source'] = rootOU['source']
            newObj['type'] = objSchema['mongoType']
            newObj['lock'] = 'false'
            newObj['policies'] = {}  # TODO: Get the proper policies

            self._fixDuplicateName(mongoObjects, objSchema, newObj)

            # Save the new object
            return newObj

        # Try to get an already exist object
        mongoObj = self.request.db[self.mongoCollectionName].find_one({'adObjectGUID': adObj.attributes['ObjectGUID'].value})
        if mongoObj is not None:
            return update_object(self, rootOU, mongoObjects, objSchema, mongoObj, adObj)
        else:
            return new_object(self, rootOU, mongoObjects, objSchema, adObj)

    def _getRootOU(self, ouSchema, xmlDomain):
        filterRootOU = {
            'path': 'root',
            'type': ouSchema['mongoType']
        }
        rootOU = self.request.db[self.mongoCollectionName].find_one(filterRootOU)
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
            for key,value in newRootOU.items():
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

    def post(self):
        try:
            #import pudb; pudb.set_trace()

            # Read GZIP data
            postedfile = self.request.POST['media'].file
            xmldata = GzipFile('', 'r', 9, StringIO(postedfile.read())).read()

            # Read XML data
            xmldoc = minidom.parseString(xmldata)

            # Get the root OU
            xmlDomain = xmldoc.getElementsByTagName('Domain')[0]
            rootOU = self._getRootOU(self.importSchema[0], xmlDomain)

            # Convert from AD objects to MongoDB objects
            mongoObjects = []
            for objSchema in self.importSchema:
                objs = xmldoc.getElementsByTagName(objSchema['adName'])
                for adObj in objs:
                    if not adObj.hasAttribute('ObjectGUID'):
                        raise Exception('An Active Directory object must has "ObjectGUID" attrib.')
                    mongoObjects.append(self._convertADObjectToMongoObject(rootOU, mongoObjects, objSchema, adObj))

            # Get & set the path for each MongoDB objects
            successCounter = 0
            mongoObjectsAlreadySaved = []
            for mongoObject in mongoObjects:
                path = ['root', str(rootOU['_id'])]
                # TODO: Get the proper path ("root,{0}._id,{1}._id,{2}._id...")
                subPath = mongoObject['adDistinguishedName'].replace(',{0}'.format(rootOU['adDistinguishedName']), '')
                m = re.findall(ur'([^, ]+=(?:(?:\\,)|[^,])+)', subPath)
                if m:
                    groupsCounter = len(m)
                    if groupsCounter > 1:
                        for i in xrange(1, groupsCounter):
                            nodePath = [rootOU['adDistinguishedName']]
                            for j in xrange(groupsCounter, i, -1):
                                nodePath.insert(0, m[j - 1])
                            nodePath = ','.join(nodePath)
                            # Find parent
                            for mongoObject2 in mongoObjects:
                                if mongoObject2['adDistinguishedName'] == nodePath:
                                    if mongoObject2 not in mongoObjectsAlreadySaved:
                                        # Save parent
                                        if self._saveMongoObject(mongoObject2):
                                            successCounter += 1
                                            mongoObjectsAlreadySaved.append(mongoObject2)
                                            path.append(str(mongoObject2['_id']))
                                            break
                                        else:
                                            return {
                                                'status': u'Can\'t save object "{0}" in db'.format(mongoObject2['adDistinguishedName']),
                                                'ok': False
                                            }
                                    else:
                                        path.append(str(mongoObject2['_id']))
                                        break
                mongoObject['path'] = ','.join(path)

            # TODO: MemberOf

            # Save each MongoDB objects
            for mongoObject in mongoObjects:
                if mongoObject not in mongoObjectsAlreadySaved:
                    if self._saveMongoObject(mongoObject):
                        successCounter += 1

            # Return result
            totalCounter = len(mongoObjects)
            return {
                'status': '{0} of {1} objects imported successfully.'.format(successCounter, totalCounter),
                'ok': True if successCounter == totalCounter else False
            }
        except Exception as e:
            return {
                'status': u'{0}'.format(e),
                'ok': False
            }

    def get_collection(self, collection=None):
        return {}
