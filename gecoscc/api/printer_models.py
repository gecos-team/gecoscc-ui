#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Alberto Beiztegui <albertobeiz@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from cornice.resource import resource

from gecoscc.api import ResourcePaginatedReadOnly
from gecoscc.models import PrinterModel, PrinterModels
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/printer_models/',
          path='/api/printer_models/{oid}/',
          description='Printer models',
          validators=(api_login_required,))
class PrinterModelsResource(ResourcePaginatedReadOnly):

    schema_collection = PrinterModels
    schema_detail = PrinterModel
    objtype = 'printer_models'

    mongo_filter = {}

    collection_name = objtype

    order_field = 'model'

    def get_distinct_filter(self, objects):
        if self.request.GET.get('manufacturers_list'):
            objects = objects.distinct('manufacturer')
            objects.sort()
            objects = [{'manufacturer': m, 'model': ''} for m in objects]
        return objects

    def set_name_filter(self, query, key_name='manufacturer'):
        if 'manufacturer' in self.request.GET:
            query.append({
                key_name: self.request.GET.get('manufacturer')
            })

        if 'imodel' in self.request.GET:
            query.append({
                'model': {
                    '$regex': u'.*{0}.*'.format(self.request.GET.get('imodel')),
                    '$options': '-i'
                }
            })
