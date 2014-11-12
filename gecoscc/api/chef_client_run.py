import datetime
import json
import pytz

from bson import json_util
from chef import Node
from cornice.resource import resource

from pyramid.threadlocal import get_current_registry

from gecoscc.api import BaseAPI
from gecoscc.models import Computer, Computers
from gecoscc.utils import USE_NODE, get_chef_api

TIME_TO_EXP = datetime.timedelta(hours=1)


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
        node = Node(node_id, api)
        if not node.attributes.to_dict():
            return {'ok': False,
                    'message': 'The node does not exists (in chef)'}
        current_use_node = node.attributes.get(USE_NODE, {})
        current_use_node_control = current_use_node.get('control', None)
        current_use_node_exp_date = current_use_node.get('exp_date', None)
        if current_use_node_exp_date:
            current_use_node_exp_date = json.loads(current_use_node_exp_date, object_hook=json_util.object_hook)
            current_use_node_exp_date = current_use_node_exp_date.astimezone(pytz.utc).replace(tzinfo=None)
            now = datetime.datetime.now()
            if now - current_use_node_exp_date > TIME_TO_EXP:
                current_use_node_control = None
        if current_use_node_control == 'client':
            return {'ok': True}
        elif current_use_node_control is None:
            exp_date = datetime.datetime.utcnow() + TIME_TO_EXP
            node.attributes.set_dotted(USE_NODE, {'control': 'client',
                                                  'exp_date': json.dumps(exp_date, default=json_util.default)})
            node.save()
            node = Node(node_id, api)
            node2 = Node(node_id, api)  # second check
            current_use_node2 = node2.attributes.get(USE_NODE, {})
            current_use_control2 = current_use_node2.get('control', None)
            if current_use_control2 == 'client':
                return {'ok': True}
        return {'ok': False,
                'message': 'The node is busy'}
