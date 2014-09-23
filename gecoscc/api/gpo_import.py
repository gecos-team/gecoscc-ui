# -*- coding: utf-8 -*-
"""
Copyright (c) 2013 Junta de Andalucia <http://www.juntadeandalucia.es> Licensed under the EUPL V.1.1
"""

import logging
import re
import types
import xmltodict

from gzip import GzipFile
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

    def post(self):
        """
        Imports and converts XML GPOs into GECOSCC from self.request
        """
        import pudb; pudb.set_trace() # FIXME DELETE DEBUG

        try:
            counter = 0
            status = ''
            ok = True

            # Read SID-GUID data
            postedfile = self.request.POST['media0'].file
            xmldata = GzipFile('', 'r', 9, StringIO(postedfile.read())).read()
            xmlsid_guid = xmltodict.parse(xmldata)
            GPOConversor.xml_sid_guid = xmlsid_guid

            # Read GPOs data
            postedfile = self.request.POST['media1'].file
            xmldata = GzipFile('', 'r', 9, StringIO(postedfile.read())).read()
            xmlgpos = xmltodict.parse(xmldata)

            # Apply each xmlgpo
            for xmlgpo in xmlgpos['report']['GPO']:
                for gpoconversorclass in GPOConversor.__subclasses__():
                    if gpoconversorclass(self.request.db).apply(xmlgpo) == False:
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
