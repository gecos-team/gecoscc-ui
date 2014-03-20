from cornice.resource import resource

from gecoscc.api import TreeLeafResourcePaginated
from gecoscc.models import User, Users
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/users/',
          path='/api/users/{oid}/',
          description='Users resource',
          validators=(api_login_required,))
class UserResource(TreeLeafResourcePaginated):

    schema_collection = Users
    schema_detail = User
    objtype = 'user'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'
