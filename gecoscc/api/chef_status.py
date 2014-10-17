import datetime

from bson import ObjectId

from chef import Node
from cornice.resource import resource

from pyramid.threadlocal import get_current_registry

from gecoscc.api import BaseAPI
from gecoscc.models import Job
from gecoscc.utils import get_chef_api, get_filter_in_domain, apply_policies_to_user
from gecoscc.socks import invalidate_jobs


@resource(path='/chef/status/',
          description='Chef callback API')
class ChefStatusResource(BaseAPI):

    schema_detail = Job
    collection_name = 'jobs'

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
        job_status = node.attributes.get('job_status')
        if job_status:
            for job_id, job_status in job_status.to_dict().items():
                job = self.collection.find_one({'_id': ObjectId(job_id)})
                if not job:
                    continue
                if job_status['status'] == 0:
                    self.collection.update({'_id': job['_id']},
                                           {'$set': {'status': 'finished',
                                                     'last_update': datetime.datetime.now()}})
                    invalidate_jobs(self.request)
                else:
                    self.collection.update({'_id': job['_id']},
                                           {'$set': {'status': 'errors',
                                                     'message': job_status.get('message', 'Error'),
                                                     'last_update': datetime.datetime.now()}})
                    invalidate_jobs(self.request)
            node.attributes.set_dotted('job_status', {})
            node.save()

        try:
            users_old = node.attributes.get_dotted('ohai_gecos.users_old')
        except KeyError:
            users_old = []
        try:
            users = node.attributes.get_dotted('ohai_gecos.users')
        except KeyError:
            users = []
        if not users_old or users_old != users:
            return self.check_users(node)
        return {'ok': True}

    def check_users(self, chef_node):
        node_collection = self.request.db.nodes
        try:
            users = chef_node.attributes.get_dotted('ohai_gecos.users')
        except KeyError:
            users = []

        node_id = chef_node.name
        node = node_collection.find_one({'node_chef_id': node_id, 'type': 'computer'})
        if not node:
            return {'ok': False,
                    'message': 'This node does not exist (mongodb)'}

        users_does_not_find = []
        users_recalculate_policies = []
        for chef_user in users:
            username = chef_user['username']
            user = node_collection.find_one({'name': username,
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
                node_collection.update({'_id': user['_id']}, {'$set': {'computers': computers}})
                users_recalculate_policies.append(user)

        for user in users_recalculate_policies:
            apply_policies_to_user(node_collection, user, self.request.user)

        chef_node.normal.set_dotted('ohai_gecos.users_old', users)
        chef_node.save()

        if users_does_not_find:
            return {'ok': False,
                    'message': 'These users does not exists: %s' % ','.join(users_does_not_find)}
        return {'ok': True}
