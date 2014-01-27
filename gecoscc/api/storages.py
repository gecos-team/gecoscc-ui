from cornice.resource import resource

from gecoscc.api import TreeLeafResourcePaginated
from gecoscc.models import Storage, Storages
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/storages/',
          path='/api/storages/{oid}/',
          description='Storages resource',
          validators=(api_login_required,))
class StorageResource(TreeLeafResourcePaginated):

    schema_collection = Storages
    schema_detail = Storage
    objtype = 'storage'

    mongo_filter = {
        'type': 'storage',
    }
    collection_name = 'nodes'
