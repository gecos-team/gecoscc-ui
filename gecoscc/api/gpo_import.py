# -*- coding: utf-8 -*-

#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Jose Luis Salvador <salvador.joseluis@gmail.com>
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import logging
import xmltodict

from gzip import GzipFile
from bson import ObjectId
from StringIO import StringIO

from cornice.resource import resource

from pyramid.httpexceptions import HTTPBadRequest

from gecoscc.api import BaseAPI
from gecoscc.api.gpoconversors import GPOConversor
from gecoscc.permissions import http_basic_login_required, can_access_to_this_path
from gecoscc.utils import is_domain

logger = logging.getLogger(__name__)


@resource(path='/api/gpo_import/',
          description='GroupPolicy import',
          validators=(http_basic_login_required,))
class GPOImport(BaseAPI):

    collection_name = 'nodes'
    collection_policies_name = 'policies'

    def __init__(self, request, context=None):
        super(GPOImport, self).__init__(request, context=context)
        self.collection_policies = self.request.db[self.collection_policies_name]

    def _cleanPrefixNamespaces(self, xml):
        if isinstance(xml, dict):
            for old_key in xml.keys():
                old_key_splitted = old_key.split(':')  # namespace prefix separator
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

            # Update domain with master_policies
            domain_id = self.request.POST.get('domainId', None)
            if not domain_id:
                raise HTTPBadRequest('GECOSCC needs a domainId param')
            filter_domain = {
                '_id': ObjectId(domain_id),
                'type': 'ou'
            }
            domain = self.collection.find_one(filter_domain)
            if not domain:
                raise HTTPBadRequest('domain does not exists')

            can_access_to_this_path(self.request, self.collection, domain, ou_type='ou_availables')

            if not is_domain(domain):
                raise HTTPBadRequest('domain param is not a domain id')

            policies_slugs = self.request.POST.getall('masterPolicy[]')
            for policy_slug in policies_slugs:
                policy = self.collection_policies.find_one({'slug': policy_slug})
                if 'master_policies' not in domain:
                    domain['master_policies'] = {}
                if policy is not None and policy['_id'] not in domain['master_policies']:
                    domain['master_policies'][str(policy['_id'])] = True
            self.collection.update(filter_domain, domain)

            # Read GPOs data
            postedfile = self.request.POST['media1'].file
            xmldata = GzipFile('', 'r', 9, StringIO(postedfile.read())).read()
            xmlgpos = xmltodict.parse(xmldata)

            # Apply each xmlgpo
            for xmlgpo in xmlgpos['report']['GPO']:
                for gpoconversorclass in GPOConversor.__subclasses__():
                    if not gpoconversorclass(self.request).apply(self._cleanPrefixNamespaces(xmlgpo)):
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
