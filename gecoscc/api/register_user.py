from cornice.resource import resource

from gecoscc.api import BaseAPI
from gecoscc.models import Node as MongoNode
from gecoscc.tasks import object_changed


@resource(path='/register/user/',
          description='Register users')
class RegisterUserResource(BaseAPI):

    schema_detail = MongoNode
    collection_name = 'nodes'

    def put(self):
        node_id = self.request.POST.get('node_id')
        usernames = self.request.POST.get('users').split(',')
        node = self.collection.find_one({'node_chef_id': node_id, 'type': 'computer'})
        if not node:
            return {'ok': False,
                    'error': 'This node does not exist (mongodb)'}
        users_does_not_find = []
        users_recalculate_policies = []
        for username in usernames:
            user = self.collection.find_one({'name': username})
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
            object_changed.delay(self.request.user, 'user', user, {})

        if users_does_not_find:
            return {'ok': False,
                    'error': 'These users does not exists: %s' % ','.join(users_does_not_find)}
        return {'ok': True}
