import datetime

from bson import ObjectId

from chef import Node
from cornice.resource import resource

from pyramid.threadlocal import get_current_registry

from gecoscc.api import BaseAPI
from gecoscc.models import Job
from gecoscc.models import User
from gecoscc.utils import (get_chef_api, get_filter_in_domain,
                           apply_policies_to_user, reserve_node_or_raise,
                           save_node_and_free)
from gecoscc.socks import invalidate_jobs, add_computer_to_user, update_tree


USERS_OLD = 'ohai_gecos.users_old'
USERS_OHAI = 'ohai_gecos.users'


@resource(path='/chef/status/',
          description='Chef callback API')
class ChefStatusResource(BaseAPI):

    schema_detail = Job
    collection_name = 'jobs'

    def get_attr(self, node, attr):
        try:
            attr_value = node.attributes.get_dotted(attr)
        except KeyError:
            attr_value = []
        return attr_value

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
            reserve_node_or_raise(node, api)
            for job_id, job_status in job_status.to_dict().items():
                job = self.collection.find_one({'_id': ObjectId(job_id)})
                if not job:
                    continue
                if job_status['status'] == 0:
                    self.collection.update({'_id': job['_id']},
                                           {'$set': {'status': 'finished',
                                                     'last_update': datetime.datetime.utcnow()}})
                else:
                    self.collection.update({'_id': job['_id']},
                                           {'$set': {'status': 'errors',
                                                     'message': job_status.get('message', 'Error'),
                                                     'last_update': datetime.datetime.utcnow()}})
            invalidate_jobs(self.request)
            node.attributes.set_dotted('job_status', {})

        users_old = self.get_attr(node, USERS_OLD)
        users = self.get_attr(node, USERS_OHAI)
        if not users_old or users_old != users:
            return self.check_users(node)
        if job_status:
            save_node_and_free(node)
        return {'ok': True}

    def check_users(self, chef_node):
        node_collection = self.request.db.nodes

        users_old = self.get_attr(chef_node, USERS_OLD)
        users = self.get_attr(chef_node, USERS_OHAI)
        node_id = chef_node.name
        node = node_collection.find_one({'node_chef_id': node_id,
                                         'type': 'computer'})
        if not node:
            return {'ok': False,
                    'message': 'This node does not exist (mongodb)'}

        users_recalculate_policies = []
        reload_clients = False
        for chef_user in users:
            username = chef_user['username']
            if chef_user in users_old or chef_user.get('sudo', False):
                continue
            user = node_collection.find_one({'name': username,
                                             'type': 'user',
                                             'path': get_filter_in_domain(node)})
            if not user:
                user_model = User()
                user = user_model.serialize({'name': username,
                                             'path': node.get('path', ''),
                                             'type': 'user',
                                             'lock': node.get('lock', ''),
                                             'source': node.get('source', '')})
                user['computers'].append(node['_id'])
                del user['_id']
                user_id = node_collection.insert(user)
                user = node_collection.find_one({'_id': user_id})
                reload_clients = True
            if 'computers' not in user:
                computers = []
            else:
                computers = user['computers']
            if node['_id'] not in computers:
                computers.append(node['_id'])
                node_collection.update({'_id': user['_id']}, {'$set': {'computers': computers}})
                users_recalculate_policies.append(user)
                add_computer_to_user(node['_id'], user['_id'])
                reload_clients = True

        if reload_clients:
            update_tree()

        chef_node.normal.set_dotted('ohai_gecos.users_old', users)
        save_node_and_free(chef_node)

        for user in users_recalculate_policies:
            apply_policies_to_user(node_collection, user, self.request.user)

        return {'ok': True}
