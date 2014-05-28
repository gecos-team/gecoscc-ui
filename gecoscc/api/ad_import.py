#!/usr/bin/python
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

    collection_name = None

    importSchema = [
        {
            'adName': 'OrganizationalUnit',
            'nodeCollectionName': 'nodes',
            'nodeType': 'ou',
            'attributes': [
                {
                    'ad': 'ObjectGUID',
                    'node': 'adObjectGUID'
                },
                {
                    'ad': 'DistinguishedName',
                    'node': 'adDistinguishedName'
                },
                {
                    'ad': 'Name',
                    'node': 'name'
                },
                {
                    'ad': 'Description',
                    'node': 'extra'
                }
            ]
        },
        {
            'adName': 'User',
            'nodeCollectionName': 'nodes',
            'nodeType': 'user',
            'attributes': [
                {
                    'ad': 'ObjectGUID',
                    'node': 'adObjectGUID'
                },
                {
                    'ad': 'DistinguishedName',
                    'node': 'adDistinguishedName'
                },
                {
                    'ad': 'Name',
                    'node': 'name'
                },
                {
                    'ad': 'Description',
                    'node': 'extra'
                }
            ]
        },
        {
            'adName': 'Group',
            'nodeCollectionName': 'nodes',
            'nodeType': 'group',
            'attributes': [
                {
                    'ad': 'ObjectGUID',
                    'node': 'adObjectGUID'
                },
                {
                    'ad': 'DistinguishedName',
                    'node': 'adDistinguishedName'
                },
                {
                    'ad': 'Name',
                    'node': 'name'
                },
                {
                    'ad': 'Description',
                    'node': 'extra'
                }
            ]
        },
        {
            'adName': 'Computer',
            'nodeCollectionName': 'nodes',
            'nodeType': 'computer',
            'attributes': [
                {
                    'ad': 'ObjectGUID',
                    'node': 'adObjectGUID'
                },
                {
                    'ad': 'DistinguishedName',
                    'node': 'adDistinguishedName'
                },
                {
                    'ad': 'Name',
                    'node': 'name'
                },
                {
                    'ad': 'Description',
                    'node': 'extra'
                }
            ]
        },
        {
            'adName': 'Printer',
            'nodeCollectionName': 'nodes',
            'nodeType': 'printer',
            'attributes': [
                {
                    'ad': 'ObjectGUID',
                    'node': 'adObjectGUID'
                },
                {
                    'ad': 'DistinguishedName',
                    'node': 'adDistinguishedName'
                },
                {
                    'ad': 'Name',
                    'node': 'name'
                },
                {
                    'ad': 'Description',
                    'node': 'extra'
                }
            ]
        },
        {
            'adName': 'Volume',
            'nodeCollectionName': 'nodes',
            'nodeType': 'storage',
            'attributes': [
                {
                    'ad': 'ObjectGUID',
                    'node': 'adObjectGUID'
                },
                {
                    'ad': 'DistinguishedName',
                    'node': 'adDistinguishedName'
                },
                {
                    'ad': 'Name',
                    'node': 'name'
                },
                {
                    'ad': 'Description',
                    'node': 'extra'
                }
            ]
        }
    ]

    def _processObject(self, source, objSchema, adObj):

        def update(self, source, objSchema, nodeObj, adObj):
            """
            Update an object from a collection with a GUID in common.
            """

            # Update NODEJS object with ACTIVE DIRECTORY attributes
            for attrib in objSchema['attributes']:
                if adObj.hasAttribute(attrib['ad']):
                    nodeObj[attrib['node']] = adObj.attributes[attrib['ad']].value

            # TODO: Save the changes
            return False

        def create(self, source, objSchema, adObj):
            """
            Create an object into a collection.
            """

            def fixDuplicateName(objSchema, newObj):
                """
                Fix ACTIVE DIRECTORY duplicate name append an _counter to the name
                """
                collection = self.request.db[objSchema['nodeCollectionName']].find({
                    'name': {
                        '$regex': u'{0}(_\d+)?'.format(newObj['name'])
                    },
                    'type': objSchema['nodeType']
                },{
                    'name': 1
                }).sort('name', -1)
                if collection.count() > 0:
                    m = re.match(r'{0}(_\d+)'.format(newObj['name']), collection[0]['name'])
                    if m:
                        newObj['name'] = '{0}_{1}'.format(newObj['name'], int(m.group(1)[1:]) + 1)
                    else:
                        newObj['name'] = '{0}_1'.format(newObj['name'])

            # Create the new NODEJS object.
            newObj = {}
            for attrib in objSchema['attributes']:
                if adObj.hasAttribute(attrib['ad']):
                    newObj[attrib['node']] = adObj.attributes[attrib['ad']].value

            # Add additional attributes.
            newObj['source'] = source
            newObj['type'] = objSchema['nodeType']
            newObj['lock'] = 'false'
            newObj['policies'] = {} # TODO: Get the proper policies
            newObj['path'] = 'root,5383163097e930c61d5a0750' # TODO: Get the proper root ("root,{0}._id,{1}._id,{2}._id...")

            fixDuplicateName(objSchema, newObj)

            # Save the new object
            return self.request.db[objSchema['nodeCollectionName']].insert(newObj)

        # An AD object must has 'ObjectGUID' attrib.
        if not adObj.hasAttribute('ObjectGUID'):
            return False

        # Try to get an already exist object
        nodeObj = self.request.db[objSchema['nodeCollectionName']].find_one({
            'adObjectGUID': adObj.attributes['ObjectGUID'].value,
            'type': objSchema['nodeType']
        })
        if nodeObj is not None:
            return update(self, source, objSchema, nodeObj, adObj)
        else:
            return create(self, source, objSchema, adObj)

    def post(self):
        try:

            import pudb; pudb.set_trace()

            # Read GZIP data
            postedfile = self.request.POST['media'].file
            xmldata = GzipFile('', 'r', 9, StringIO(postedfile.read())).read()

            # Read XML data
            xmldoc = minidom.parseString(xmldata)

            # Get global domain info.
            xmlDomain = xmldoc.getElementsByTagName('Domain')[0]
            source = 'ad:{0}:{1}'.format(xmlDomain.attributes['DistinguishedName'].value, xmlDomain.attributes['ObjectGUID'].value)

            # Import each object from AD
            totalCounter = 0
            successCounter = 0
            for objSchema in self.importSchema:
                objs = xmldoc.getElementsByTagName(objSchema['adName'])
                for adObj in objs:
                    totalCounter += 1
                    if self._processObject(source, objSchema, adObj):
                        successCounter += 1

            # Return result
            return {
                'status': '{0} of {1} objects imported successfully.'.format(successCounter, totalCounter),
                'ok': True if successCounter == totalCounter else False
            }
        except:
            raise HTTPInternalServerError("An internal error has occurred.")

    def get_collection(self, collection=None):
        return {}
