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

from bson import ObjectId

from cornice.resource import resource

from pyramid.threadlocal import get_current_registry

from gecoscc.api import BaseAPI
from gecoscc.models import Node as MongoNode
from gecoscc.permissions import http_basic_login_required
from gecoscc.utils import get_chef_api, register_node, apply_policies_to_computer
from gecoscc.socks import delete_computer, update_tree, invalidate_change, invalidate_delete 
from gecoscc.eventsmanager import JobStorage

import logging
logger = logging.getLogger(__name__)

@resource(path='/register/computer/',
          description='Register computer from chef',
          validators=http_basic_login_required)
class RegisterComputerResource(BaseAPI):

    schema_detail = MongoNode
    collection_name = 'nodes'

    def post(self):
        ou_id = self.request.POST.get('ou_id')
        node_id = self.request.POST.get('node_id')
        ou = None
        if ou_id:
            ou = self.collection.find_one({'_id': ObjectId(ou_id), 'type': 'ou'})
        else:
            ou_availables = self.request.user.get('ou_availables')
            if isinstance(ou_availables, list) and len(ou_availables) > 0:
                ou = self.collection.find_one({'_id': {'$in': [ObjectId(ou_ava_id) for ou_ava_id in ou_availables]},
                                               'type': 'ou',
                                               'path': {'$ne': 'root'}})
        if not ou:
            return {'ok': False,
                    'message': 'Ou does not exists'}

        settings = get_current_registry().settings
        api = get_chef_api(settings, self.request.user)
        computer_id = register_node(api, node_id, ou, self.collection)
        if not computer_id:
            return {'ok': False,
                    'message': 'Node does not exist (in chef)'}
        elif computer_id == 'duplicated':
            return {'ok': False,
                    'message': 'There is another node with this name (in gcc)'}
        elif computer_id == 'duplicated-node-id':
            return {'ok': False,
                    'message': 'There is another node with this node chef id (in gcc)'}
        elif computer_id == 'path-err':
            return {'ok': False,
                    'message': 'Unable to add gecos path ids and names to chef node'}            

        computer = self.collection.find_one({'_id': computer_id})
        apply_policies_to_computer(self.collection, computer, self.request.user)
        update_tree(computer['path'])
        return {'ok': True}

    def put(self):
        node_id = self.request.POST.get('node_id')
        computer = self.collection.find_one({'node_chef_id': node_id})
        if not computer:
            return {'ok': False,
                    'message': 'Computer does not exists'}
        apply_policies_to_computer(self.collection, computer, self.request.user)
        invalidate_change(self.request, computer)
        return {'ok': True}

    def delete(self):
        node_id = self.request.GET.get('node_id')
        logger.info("/register/computer: Deleting computer for node_id = %s" % (str(node_id)))
        # Find the computer node
        computer = self.collection.find_one({'node_chef_id': node_id})
        
        # Delete the reference from users
        users = self.collection.find({'computers': computer['_id'], 'type': 'user'})
        for user in users:
            logger.info("/register/computer: Removing computer %s relationship from user %s" % (str(computer['_id']), str(user['_id'])))
            self.collection.update({'_id': user['_id']}, {'$pull': { 'computers': computer['_id'] }})
        
        # Delete the computer node
        node_deleted = self.collection.remove({'node_chef_id': node_id, 'type': 'computer'})
        num_node_deleted = node_deleted['n']
        if num_node_deleted >= 1:
            # Create a job so the administrator can see the 'detached' action
            job_storage = JobStorage(self.request.db.jobs, self.request.user)
            job_storage.create(obj=computer,
                            op='detached',
                            status='finished',
                            message=self._("Pending: %d") %(0),
                            policy={'name':'detached computer',
                                    'name_es':self._('detached') + " " + self._('computer')},
                            administrator_username=self.request.user['username'])
        

            invalidate_delete(self.request, computer)
            if num_node_deleted == 1:
                delete_computer(computer['_id'], computer['path'])
                return {'ok': True}
            return {'ok': False,
                    'message': 'Deleted %s computers' % num_node_deleted}
        elif num_node_deleted < 1:
            return {'ok': False,
                    'message': 'This node does not exist (mongodb)'}
