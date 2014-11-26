from cornice.resource import resource

from bson import ObjectId

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

    def get(self):
        result = super(UserResource, self).get()
        computers_ids = [ObjectId(c) for c in result.get('computers')]
        node_collection = self.request.db.nodes

        computers = node_collection.find({'_id': {'$in': computers_ids},'type': 'computer'})
        computer_names = [computer['name'] for computer in computers]

        result.update({'computer_names': computer_names})
        return result
