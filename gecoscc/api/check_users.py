from chef import Node as ChefNode
from cornice.resource import resource

from pyramid.threadlocal import get_current_registry

from gecoscc.api import BaseAPI
from gecoscc.models import Node as MongoNode
from gecoscc.utils import (get_chef_api, get_filter_in_domain,
                           apply_policies_to_user)


@resource(path='/check/user/',
          description='Check users')
class RegisterUserResource(BaseAPI):

    schema_detail = MongoNode
    collection_name = 'nodes'

    def put(self):
        node_id = self.request.POST.get('node_id')
        gcc_username = self.request.POST.get('gcc_username')
        node = self.collection.find_one({'node_chef_id': node_id, 'type': 'computer'})
        if not node:
            return {'ok': False,
                    'message': 'This node does not exist (mongodb)'}
        if not gcc_username:
            return {'ok': False,
                    'message': 'Please set a admin username (gcc_username)'}

        settings = get_current_registry().settings
        self.request.user = self.request.db.adminusers.find_one({'username': gcc_username})
        if not self.request.user:
            return {'ok': False,
                    'message': 'The admin user %s does not exists' % gcc_username}
        api = get_chef_api(settings, self.request.user)
        chef_node = ChefNode(node_id, api)
        try:
            users = chef_node.attributes.get_dotted('ohai_gecos.users')
        except KeyError:
            users = []

        users_does_not_find = []
        users_recalculate_policies = []
        for chef_user in users:
            username = chef_user['username']
            user = self.collection.find_one({'name': username,
                                             'path': get_filter_in_domain(node)})
            if not user:
                users_does_not_find.append(username)
                continue
            if 'computers' not in user:
                computers = []
            else:
                computers = user['computers']
            if node['_id'] not in computers:
                computers.append(node['_id'])
                self.collection.update({'_id': user['_id']}, {'$set': {'computers': computers}})
                users_recalculate_policies.append(user)

        for user in users_recalculate_policies:
            apply_policies_to_user(self.collection, user, self.request.user)

        if users_does_not_find:
            return {'ok': False,
                    'message': 'These users does not exists: %s' % ','.join(users_does_not_find)}
        return {'ok': True}
