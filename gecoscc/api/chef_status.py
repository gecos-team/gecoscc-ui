#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import datetime
import random

from bson import ObjectId
from copy import deepcopy

from chef import Node
from cornice.resource import resource

from pyramid.threadlocal import get_current_registry

from gecoscc.api import BaseAPI
from gecoscc.models import Job
from gecoscc.models import User
from gecoscc.utils import (get_chef_api, get_filter_in_domain,
                           apply_policies_to_user, remove_policies_of_computer,
                           reserve_node_or_raise, save_node_and_free, update_computers_of_user)
from gecoscc.socks import invalidate_jobs, invalidate_change, add_computer_to_user, update_tree

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

        # After chef-client run, a report handler calls /api/chef_status
        # Previously, gcc_link attribute of chef node is updated by network policies
        gcc_link = node.attributes.get('gcc_link')
        self.request.db.nodes.update({'node_chef_id':node_id},{'$set': {'gcc_link':gcc_link}})

        reserve_node = False
        if job_status:
            node = reserve_node_or_raise(node_id, api, 'gcc-chef-status-%s' % random.random(), attempts=3)
            reserve_node = True
            chef_client_error = False

            for job_id, job_status in job_status.to_dict().items():
                job = self.collection.find_one({'_id': ObjectId(job_id)})
                if not job:
                    continue
                # Parent
                macrojob = self.collection.find_one({'_id': ObjectId(job['parent'])}) if 'parent' in job else None
                if job_status['status'] == 0:
                    self.collection.update({'_id': job['_id']},
                                           {'$set': {'status': 'finished',
                                                     'last_update': datetime.datetime.utcnow()}})
                    # Decrement number of children in parent
                    if macrojob and 'counter' in macrojob:
                        macrojob['counter'] -= 1
                elif job_status['status'] == 2:
                    self.collection.update({'_id': job['_id']},
                                           {'$set': {'status': 'warnings',
                                                     'message': job_status.get('message', 'Warning'),
                                                     'last_update': datetime.datetime.utcnow()}})
                    if macrojob:                                
                        macrojob['status'] = 'warnings'
                else:
                    chef_client_error = True
                    self.collection.update({'_id': job['_id']},
                                           {'$set': {'status': 'errors',
                                                     'message': job_status.get('message', 'Error'),
                                                     'last_update': datetime.datetime.utcnow()}})
                    if macrojob:                                
                        macrojob['status'] = 'errors'
                # Update parent                                 
                if macrojob:
                    self.collection.update({'_id': macrojob['_id']},                                                                
                                           {'$set': {'counter': macrojob['counter'],
                                                     'message': self._("Pending: %d") % macrojob['counter'],
                                                     'status': 'finished' if macrojob['counter'] == 0 else macrojob['status']}})
            self.request.db.nodes.update({'node_chef_id': node_id}, {'$set': {'error_last_chef_client': chef_client_error}})
            invalidate_jobs(self.request)
            node.attributes.set_dotted('job_status', {})

        users_old = self.get_attr(node, USERS_OLD)
        users = self.get_attr(node, USERS_OHAI)
        if not users_old or users_old != users:
            if not reserve_node:
                node = reserve_node_or_raise(node_id, api, 'gcc-chef-status-%s' % random.random(), attempts=3)
            return self.check_users(node, api)
        if job_status:
            save_node_and_free(node)
        return {'ok': True}

    def check_users(self, chef_node, api):
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

                user = update_computers_of_user(self.request.db, user, api)

                del user['_id']
                user_id = node_collection.insert(user)
                user = node_collection.find_one({'_id': user_id})
                reload_clients = True
                users_recalculate_policies.append(user)
            else:
                computers = user.get('computers', [])
                if node['_id'] not in computers:
                    computers.append(node['_id'])
                    node_collection.update({'_id': user['_id']}, {'$set': {'computers': computers}})
                    users_recalculate_policies.append(user)
                    add_computer_to_user(node['_id'], user['_id'])
                    invalidate_change(self.request, user)

        users_remove_policies = []

        for chef_user in users_old:
            username = chef_user['username']
            if chef_user in users or chef_user.get('sudo', False):
                continue
            user = node_collection.find_one({'name': username,
                                             'type': 'user',
                                             'path': get_filter_in_domain(node)})
            computers = user['computers'] if user else []
            if node['_id'] in computers:
                users_remove_policies.append(deepcopy(user))
                computers.remove(node['_id'])
                node_collection.update({'_id': user['_id']}, {'$set': {'computers': computers}})
                invalidate_change(self.request, user)

        if reload_clients:
            update_tree(node.get('path', ''))

        chef_node.normal.set_dotted(USERS_OLD, users)
        save_node_and_free(chef_node)

        for user in users_recalculate_policies:
            apply_policies_to_user(node_collection, user, self.request.user)

        for user in users_remove_policies:
            remove_policies_of_computer(user, node, self.request.user)

        return {'ok': True}
