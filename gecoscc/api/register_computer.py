from bson import ObjectId

from cornice.resource import resource

from pyramid.threadlocal import get_current_registry

from gecoscc.api import BaseAPI
from gecoscc.models import Node as MongoNode
from gecoscc.permissions import http_basic_login_required
from gecoscc.tasks import object_changed, object_created
from gecoscc.utils import get_chef_api, register_node, get_filter_ous_from_path


@resource(path='/register/computer/',
          description='Register computer from chef',
          validators=http_basic_login_required)
class RegisterComputerResource(BaseAPI):

    schema_detail = MongoNode
    collection_name = 'nodes'

    def apply_policies_to_computer(self, computer):
        ous = self.collection.find(get_filter_ous_from_path(computer['path']))
        for ou in ous:
            object_changed.delay(self.request.user, 'ou', ou, {}, computers=[computer])
        object_created.delay(self.request.user, 'computer', computer, computers=[computer])

    def post(self):
        ou_id = self.request.POST.get('ou_id')
        node_id = self.request.POST.get('node_id')
        ou = None
        if ou_id:
            ou = self.collection.find_one({'_id': ObjectId(ou_id), 'type': 'ou'})
        else:
            ou_availables = self.request.user.get('ou_availables')
            if isinstance(ou_availables, list) and len(ou_availables) > 0:
                ou = self.collection.find_one({'_id': ObjectId(ou_availables[0]), 'type': 'ou'})
            else:
                if self.request.user.get('is_superuser'):
                    ou = self.collection.find_one({'path': 'root', 'type': 'ou'})
        if not ou:
            return {'ok': False,
                    'error': 'Ou does not exists'}

        settings = get_current_registry().settings
        api = get_chef_api(settings, self.request.user)
        computer_id = register_node(api, node_id, ou, self.collection)
        if not computer_id:
            return {'ok': False,
                    'error': 'Node does not exist (in chef)'}
        computer = self.collection.find_one({'_id': computer_id})
        self.apply_policies_to_computer(computer)
        return {'ok': True}

    def delete(self):
        node_id = self.request.GET.get('node_id')
        node_deleted = self.collection.remove({'node_chef_id': node_id, 'type': 'computer'})
        num_node_deleted = node_deleted['n']
        if num_node_deleted == 1:
            return {'ok': True}
        elif num_node_deleted < 1:
            return {'ok': False,
                    'error': 'This node does not exist (mongodb)'}
        elif num_node_deleted > 1:
            return {'ok': False,
                    'error': 'Deleted %s computers' % num_node_deleted}
