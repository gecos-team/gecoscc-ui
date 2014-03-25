from cornice.resource import resource

from gecoscc.api import TreeLeafResourcePaginated
from gecoscc.models import Repository, Repositories
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/repositories/',
          path='/api/repositories/{oid}/',
          description='Repositories resource',
          validators=(api_login_required,))
class RepositoryResource(TreeLeafResourcePaginated):

    schema_collection = Repositories
    schema_detail = Repository
    objtype = 'repository'

    mongo_filter = {
        'type': 'repository',
    }
    collection_name = 'nodes'
