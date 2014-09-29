from cornice.resource import resource

from gecoscc.api import BaseAPI
from gecoscc.models import Computer, Computers
from gecoscc.permissions import http_basic_login_required


@resource(path='/computers/list/',
          description='Computers public API',
          validators=(http_basic_login_required,))
class ComputerPublicResource(BaseAPI):

    schema_collection = Computers
    schema_detail = Computer
    objtype = 'computer'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'

    def get(self):
        computers = [{'node_chef_id': comp['node_chef_id'],
                      'name': comp['name']} for comp in self.collection.find({'type': self.objtype})]
        return {'computers': computers}