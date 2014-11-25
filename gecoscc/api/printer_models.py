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

    def get_distinct_filter(self, objects):
        if self.request.GET.get('manufacturers_list'):
            objects = objects.distinct('manufacturer')
            objects = [{'manufacturer':m, 'model':''} for m in objects]
        return objects
