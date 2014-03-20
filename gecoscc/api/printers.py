from cornice.resource import resource

from gecoscc.api import TreeLeafResourcePaginated
from gecoscc.models import Printer, Printers
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/printers/',
          path='/api/printers/{oid}/',
          description='Printers resource',
          validators=(api_login_required,))
class PrinterResource(TreeLeafResourcePaginated):

    schema_collection = Printers
    schema_detail = Printer
    objtype = 'printer'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'
