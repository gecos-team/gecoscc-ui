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
        computer_node = ChefNode(result['node_chef_id'], api)
        ohai = computer_node.attributes.to_dict()
        result.update({'ohai': ohai,
                       'users': ','.join([i['username'] for i in ohai.get('ohai_gecos', {}).get('users', [])]),
                       'uptime': ohai['uptime'],
                       'cpu': '%s %s' % (ohai['cpu']['0']['vendor_id'], ohai['cpu']['0']['model_name']),
                       'product_name': ohai['dmi']['system']['product_name'],
                       'manufacturer': ohai['dmi']['system']['manufacturer'],
                       'ram': ohai['dmi']['processor'].get('size', ''),
                       'lsb': ohai.get('lsb', {}),
                       'kernel': ohai.get('kernel', {}),
                       'filesystem': ohai.get('filesystem', {}),
                       })
        return result


@resource(path='/computers/ohai/{oid}/',
          description='Computers public API',
          validators=(api_login_required,))
class ComputerOahiResource(TreeLeafResourcePaginated):

    schema_collection = Computers
    schema_detail = Computer
    objtype = 'computer'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'

    def get(self):
        oid = self.request.matchdict['oid']
        collection_filter = self.get_oid_filter(oid)
        collection_filter.update(self.get_object_filter())
        collection_filter.update(self.mongo_filter)
        node = self.collection.find_one(collection_filter)

        return computer_node.attributes.to_dict()
