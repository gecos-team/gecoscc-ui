from cornice.resource import resource

from gecoscc.api import BaseAPI
from gecoscc.models import Node as MongoNode
from gecoscc.tasks import object_changed
from gecoscc.utils import get_filter_ous_from_path, get_computer_of_user


@resource(path='/register/user/',
          description='Register users')
class RegisterUserResource(BaseAPI):

    schema_detail = MongoNode
    collection_name = 'nodes'

    def apply_policies_to_user(self, user):
        computers = get_computer_of_user(self.collection, user)
        if not computers:
            return
        ous = self.collection.find(get_filter_ous_from_path(user['path']))
        for ou in ous:
            object_changed.delay(self.request.user, 'ou', ou, {}, computers=computers)
        groups = self.collection.find({'_id': {'$in': user.get('memberof', [])}})
        for group in groups:
            object_changed.delay(self.request.user, 'group', group, {}, computers=computers)
        object_changed.delay(self.request.user, 'user', user, {}, computers=computers)

    def put(self):
        node_id = self.request.POST.get('node_id')
        gcc_username = self.request.POST.get('gcc_username')
        usernames = self.request.POST.get('users').split(',')
        node = self.collection.find_one({'node_chef_id': node_id, 'type': 'computer'})
        if not node:
            return {'ok': False,
                    'error': 'This node does not exist (mongodb)'}
        if not gcc_username:
            return {'ok': False,
                    'message': 'Please set a admin username (gcc_username)'}
        self.request.user = self.request.db.adminusers.find_one({'username': gcc_username})

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
            self.apply_policies_to_user(user)

        if users_does_not_find:
            return {'ok': False,
                    'error': 'These users does not exists: %s' % ','.join(users_does_not_find)}
        return {'ok': True}
