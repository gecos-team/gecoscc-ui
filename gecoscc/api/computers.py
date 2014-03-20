from cornice.resource import resource

from gecoscc.api import TreeLeafResourcePaginated
from gecoscc.models import Computer, Computers
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/computers/',
          path='/api/computers/{oid}/',
          description='Computers resource',
          validators=(api_login_required,))
class ComputerResource(TreeLeafResourcePaginated):

    schema_collection = Computers
    schema_detail = Computer
    objtype = 'computer'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'
