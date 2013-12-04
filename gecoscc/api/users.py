from cornice.resource import resource

from gecoscc.api import ResourcePaginated
from gecoscc.models import User, Users
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/users/',
          path='/api/users/{oid}/',
          description='Users resource',
          validators=(api_login_required,))
class UserResource(ResourcePaginated):

    schema_collection = Users
    schema_detail = User

    mongo_filter = {
        'type': 'user',
    }
    collection_name = 'nodes'
