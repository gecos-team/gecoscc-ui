import urllib2

from cornice.resource import resource
from chef import Node as ChefNode
from gecoscc.utils import get_chef_api


from gecoscc.api import TreeLeafResourcePaginated
from gecoscc.models import Computer, Computers
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/computers/',
          path='/api/computers/{oid}/',
          description='Computers resource',
          validators=(api_login_required,))
class ComputerResource(TreeLeafResourcePaginated):

    schema_collection = Computers
    schema_detail = Computer
    objtype = 'computer'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'

    def get(self):
        result = super(ComputerResource, self).get()
        api = get_chef_api(self.request.registry.settings, self.request.user)
        try:
            computer_node = ChefNode(result['node_chef_id'], api)
            ohai = computer_node.attributes.to_dict()
            cpu = ohai.get('cpu', {}).get('0', {})
            dmi = ohai.get('dmi', {})
            result.update({'ohai': ohai,
                           'users': ','.join([i['username'] for i in ohai.get('ohai_gecos', {}).get('users', [])]),
                           'uptime': ohai.get('uptime', ''),
                           'cpu': '%s %s' % (cpu.get('vendor_id', ''), cpu.get('model_name', '')),
                           'product_name': dmi.get('system', {}).get('product_name', ''),
                           'manufacturer': dmi.get('system', {}).get('manufacturer', ''),
                           'ram': dmi.get('processor', {}).get('size', ''),
                           'lsb': ohai.get('lsb', {}),
                           'kernel': ohai.get('kernel', {}),
                           'filesystem': ohai.get('filesystem', {}),
                           })
        except urllib2.URLError:
            pass
        return result
