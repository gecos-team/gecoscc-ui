from cornice.resource import resource

from pyramid.threadlocal import get_current_registry

from chef import Node as ChefNode

from gecoscc.api import BaseAPI
from gecoscc.models import Node as MongoNode
from gecoscc.permissions import http_basic_login_required
from gecoscc.utils import get_chef_api


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
        node = ChefNode(node_id, api)
        if not node.attributes.to_dict():
            return {'ok': False,
                    'error': 'Node does not exists (in chef)'}
        computer_name = node.attributes.get_dotted('ohai_gecos.pclabel')
        self.collection.insert({'path': '%s,%s' % (ou['path'], unicode(ou['_id'])),
                                'name': computer_name,
                                'type': 'computer',
                                'lock': False,
                                'source': 'gecos',
                                'memberof': [],
                                'policies': {},
                                'registry': '',
                                'family': 'desktop',
                                'node_chef_id': node_id})
        return {'ok': True}