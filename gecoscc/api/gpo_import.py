# -*- coding: utf-8 -*-
"""
Copyright (c) 2013 Junta de Andalucia <http://www.juntadeandalucia.es> Licensed under the EUPL V.1.1
"""

import logging
import re
import types
import xmltodict

from gzip import GzipFile
from bson import ObjectId
from StringIO import StringIO

from cornice.resource import resource

from gecoscc.api import BaseAPI
from gecoscc.permissions import http_basic_login_required
from gecoscc.api.gpoconversors import GPOConversor

logger = logging.getLogger(__name__)

@resource(path='/api/gpo_import/',
          description='GroupPolicy import',
          validators=http_basic_login_required)
class GPOImport(BaseAPI):

    mongoCollectionNodesName = 'nodes'
    mongoCollectionPoliciesName = 'policies'

    def _cleanPrefixNamespaces(self, xml):
        if isinstance(xml, dict):
            for old_key in xml.keys():
                old_key_splitted = old_key.split(':') # namespace prefix separator
                new_key = ':'.join(old_key_splitted[1:]) if len(old_key_splitted) > 1 else old_key
                xml[new_key] = self._cleanPrefixNamespaces(xml.pop(old_key))
        if isinstance(xml, list):
            for index, subxml in enumerate(xml):
                xml[index] = self._cleanPrefixNamespaces(subxml)
        return xml

    def post(self):
        """
        Imports and converts XML GPOs into GECOSCC from self.request
        """

        try:
            counter = 0
            status = ''
            ok = True

            # Read SID-GUID data
            postedfile = self.request.POST['media0'].file
            xmldata = GzipFile('', 'r', 9, StringIO(postedfile.read())).read()
            xmlsid_guid = xmltodict.parse(xmldata)
            GPOConversor.xml_sid_guid = xmlsid_guid

            # Update rootOU with master_policies
            rootOUID = self.request.POST['rootOU']
            rootOU = None
            if rootOUID not in [None, '', 'root']:
                filterRootOU = {
                    '_id': ObjectId(rootOUID),
                    'type': 'ou'
                }
                rootOU = self.request.db[self.mongoCollectionNodesName].find_one(filterRootOU)
                policies_slugs = self.request.POST.getall('masterPolicy[]')
                for policy_slug in policies_slugs:
                    policy = self.request.db[self.mongoCollectionPoliciesName].find_one({'slug':policy_slug})
                    if policy is not None and policy['_id'] not in rootOU['master_policies']:
                        rootOU['master_policies'].append(policy['_id'])
                self.request.db[self.mongoCollectionNodesName].update(filterRootOU, rootOU)

            # Read GPOs data
            postedfile = self.request.POST['media1'].file
            xmldata = GzipFile('', 'r', 9, StringIO(postedfile.read())).read()
            xmlgpos = xmltodict.parse(xmldata)

            # Apply each xmlgpo
            for xmlgpo in xmlgpos['report']['GPO']:
                for gpoconversorclass in GPOConversor.__subclasses__():
                    if gpoconversorclass(self.request.db).apply(self._cleanPrefixNamespaces(xmlgpo)) == False:
                        # TODO Report error to somewhere
                        ok = False
                    else:
                        counter += 1

            status = 'Policies applied correctly: {0}'.format(counter)

        except Exception as e:
            logger.exception(e)
            status = u'{0}'.format(e)
            ok = False

        return {
            'status': status,
            'ok': ok
        }

    def get_collection(self, collection=None):
        return {}
