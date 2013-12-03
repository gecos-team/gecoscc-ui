from gecoscc.models import User, Users
from gecoscc.api import ResourcePaginated

from cornice.resource import resource


@resource(collection_path='/api/users/',
          path='/api/users/{oid}/',
          description='Users resource')
class UserResource(ResourcePaginated):

    schema_collection = Users
    schema_detail = User

    mongo_filter = {
        'type': 'user',
    }
    collection_name = 'nodes'
