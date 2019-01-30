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

from cornice.resource import resource

from pyramid.threadlocal import get_current_registry

from gecoscc.api import BaseAPI
from gecoscc.models import Computer, Computers
from gecoscc.utils import get_chef_api, is_node_busy_and_reserve_it

import json
import time

import logging
logger = logging.getLogger(__name__)


@resource(path='/chef-client/run/',
          description='Set chef in node')
class ChefClientRunResource(BaseAPI):

    schema_collection = Computers
    schema_detail = Computer

    collection_name = 'nodes'

    def put(self):
        """
        Reserve the Chef node before running the Chef client
        """
                
        # Check the parameters
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
        
        logger.info("/chef-client/run/: Reserve chef node %s" % (str(node_id)))

        # Saving last agent run time 
        self.request.db.nodes.update({'node_chef_id': node_id},{'$set': {'last_agent_run_time': int(time.time())}})
        
        # Reserve the node
        settings = get_current_registry().settings
        api = get_chef_api(settings, self.request.user)
        node, is_busy = is_node_busy_and_reserve_it(node_id, api, 'client', attempts=3)
        if not node.attributes.to_dict():
            return {'ok': False,
                    'message': 'The node does not exists (in chef)'}
        if is_busy:
            return {'ok': False,
                    'message': 'The node is busy'}
        return {'ok': True}


    def post(self):
        """
        Imports log files into mongoDB node
        """

        # Check the parameters
        node_id = self.request.POST.get('node_id')
        if not node_id:
            return {'ok': False,
                    'message': 'Please set a node id (node_id)'}
            
        computer = self.collection.find_one({"node_chef_id": node_id, "type": "computer"})
        if not computer:
            return {'ok': False,
                    'message': 'Can\' find a computer with this node id'}
        
        
        username = self.request.POST.get('gcc_username')
        if not username:
            return {'ok': False,
                    'message': 'Please set a admin username (gcc_username)'}
            
        self.request.user = self.request.db.adminusers.find_one({'username': username})
        if not self.request.user:
            return {'ok': False,
                    'message': 'The admin user %s does not exists' % username}
        
        logger.info("/chef-client/run/: Import logs from chef node %s" % (str(node_id)))
        
        logs = self.request.POST.get('logs')
        if not logs:
            return {'ok': False,
                    'message': 'Please set logs data (logs)'}
        
        #logger.info("/chef-client/run/: Logs = %s" % (logs))
        logs_data = None
        try:
            logs_data = json.loads(logs)
        except ValueError:
            return {'ok': False,
                    'message': 'Please set logs data (logs) as a JSON'}
            
        if not 'date' in logs_data:
            return {'ok': False,
                    'message': 'Please set a date for logs data'}
            
        if not 'files' in logs_data:
            return {'ok': False,
                    'message': 'Please set a files section in logs data'}

        # Remove dot from filenames
        computer['logs'] = {}
        computer['logs']['date'] = logs_data['date']
        computer['logs']['files'] = []
        for filename in logs_data['files']:
            filedata = {}
            filedata['filename'] = filename
            filedata['content'] = logs_data['files'][filename]
            filedata['size'] = len(logs_data['files'][filename])
            
            computer['logs']['files'].append(filedata)
            
        # Save logs data
        self.collection.update({"node_chef_id": node_id, "type": "computer"}, computer)
        
        return {'ok': True,
                    'message': 'Log data saved'}
        
