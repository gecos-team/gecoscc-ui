from cornice.resource import resource

from gecoscc.api import TreeLeafResourcePaginated
from gecoscc.models import Computer, Computers
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/printers/',
          path='/api/printers/{oid}/',
          description='Printers resource',
          validators=(api_login_required,))
class ComputerResource(TreeLeafResourcePaginated):

    schema_collection = Computers
    schema_detail = Computer
    objtype = 'printer'

    mongo_filter = {
        'type': 'printer',
    }
    collection_name = 'nodes'
