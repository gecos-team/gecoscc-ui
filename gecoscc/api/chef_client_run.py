from cornice.resource import resource

from pyramid.threadlocal import get_current_registry

from gecoscc.api import BaseAPI
from gecoscc.models import Computer, Computers
from gecoscc.utils import get_chef_api, is_node_busy_and_reserve_it


@resource(path='/chef-client/run/',
          description='Set chef in node')
class ChefClientRunResource(BaseAPI):

    schema_collection = Computers
    schema_detail = Computer
    objtype = 'computer'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'

    def put(self):
        node_id = self.request.POST.get('node_id')
        username = self.request.POST.get('gcc_username')
        if not node_id:
            return {'ok': False,
                    'message': 'Please set a node id (node_id)'}
        if not username:
            return {'ok': False,
                    'message': 'Please set a admin username (gcc_username)'}
        self.request.user = self.request.db.adminusers.find_one({'username': username})
        if not self.request.user:
            return {'ok': False,
                    'message': 'The admin user %s does not exists' % username}
        settings = get_current_registry().settings
        api = get_chef_api(settings, self.request.user)
        node, is_busy = is_node_busy_and_reserve_it(node_id, api, 'client', attempts=3)
        if not node.attributes.to_dict():
            return {'ok': False,
                    'message': 'The node does not exists (in chef)'}
        if is_busy:
            return {'ok': False,
                    'message': 'The node is busy'}
        return {'ok': True}
