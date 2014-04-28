from cornice.resource import resource

from pyramid.threadlocal import get_current_registry

from gecoscc.api import BaseAPI
from gecoscc.models import Node as MongoNode
from gecoscc.permissions import http_basic_login_required
from gecoscc.utils import get_chef_api, register_node


@resource(path='/register/computer/',
          description='Register computer from chef',
          validators=http_basic_login_required)
class RegisterComputerResource(BaseAPI):

    schema_detail = MongoNode
    collection_name = 'nodes'

    def post(self):
        ou_name = self.request.POST.get('ou_name')
        node_id = self.request.POST.get('node_id')
        ou = self.collection.find_one({'name': ou_name, 'type': 'ou'})
        settings = get_current_registry().settings
        if not ou:
            return {'ok': False,
                    'error': 'Ou does not exists'}
        api = get_chef_api(settings, self.request.user)
        node_id = register_node(api, node_id, ou, self.collection)
        if not node_id:
            return {'ok': False,
                    'error': 'Node does not exists (in chef)'}
        return {'ok': True}