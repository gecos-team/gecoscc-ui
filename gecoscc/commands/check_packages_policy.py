#
# Copyright 2017, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Abraham Macias <amacias@solutia-it.es>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import os
import sys
import string
import random
import subprocess
import json

from chef.exceptions import ChefServerNotFoundError, ChefServerError
from chef import Node as ChefNode
from chef import Search
from getpass import getpass
from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.userdb import UserAlreadyExists
from gecoscc.utils import _get_chef_api, create_chef_admin_user, toChefUsername, apply_policies_to_ou, apply_policies_to_group, apply_policies_to_computer
from bson.objectid import ObjectId
from gecoscc.models import Policy


import logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)    
    
# Execute with: 
# /opt/gecosccui-development/bin/pmanage /opt/gecosccui-development/gecoscc.ini check_packages_policy -a superuser -k /opt/gecoscc/media/users/superuser/chef_user.pem 2>&1 | grep -v InsecureRequestWarning | grep -v requests.packages.urllib3.connectionpool | tee /root/check_packages_policy.log
class Command(BaseCommand):
    description = """
       Check the policies data for all the workstations in the database looking for old packages policy data
       and adapting the data to the new packages policy structure.       
       
    """

    usage = "usage: %prog config_uri check_packages_policy --administrator user --key file.pem"

    option_list = [
        make_option(
            '-a', '--administrator',
            dest='chef_username',
            action='store',
            help='An existing chef super administrator username (like "pivotal" user)'
        ),
        make_option(
            '-k', '--key',
            dest='chef_pem',
            action='store',
            help='The pem file that contains the chef administrator private key'
        ),
    ]

    required_options = (
        'chef_username',
        'chef_pem',
    )
    
    
    def command(self):
        # Initialization
        self.api = _get_chef_api(self.settings.get('chef.url'),
                            toChefUsername(self.options.chef_username),
                            self.options.chef_pem, False, self.settings.get('chef.version'))

        self.auth_user = self.db.adminusers.find_one({'username': self.options.chef_username})       
        if self.auth_user is None:
            logger.error('The administrator user must exist in MongoDB')
            return
        

        self.db = self.pyramid.db

        # Get packages policy ID
        packages_policy = self.db.policies.find_one({"slug": "package_res"})
        if packages_policy is None:
            logger.error('Can\'t detect "package_res" policy!')
            return
            
        if 'pkgs_to_remove' in packages_policy["schema"]["properties"]:
            logger.error("The 'package_res' policy in the system is deprecated, please update to new package policy!")
            return
        
            
        logger.info('Packages policy ID: %s'%(str(packages_policy['_id'])))
        
        # Get all nodes with old package policy data
        logger.info('Getting all nodes with old package policy data...')
        path_to_find = "policies.%s.pkgs_to_remove"%(str(packages_policy['_id']))
        old_policy_nodes = self.db.nodes.find({path_to_find: { '$exists': True }})
        
        
        updated_nodes = []
        for node in old_policy_nodes:
            logger.info('Updating node %s ...'%(str(node['_id'])))
            updated_nodes.append(str(node['_id']))
            
            logger.debug('Packages to add: %s'%(str(node['policies'][str(packages_policy['_id'])]['package_list'])))
            logger.debug('Packages to remove: %s'%(str(node['policies'][str(packages_policy['_id'])]['pkgs_to_remove'])))
            
            # Join the lists
            package_list = []
            for package_name in node['policies'][str(packages_policy['_id'])]['package_list']:
                package_list.append({'name': package_name, 'version': 'current', 'action': 'add'})
            
            for package_name in node['policies'][str(packages_policy['_id'])]['pkgs_to_remove']:
                package_list.append({'name': package_name, 'version': 'current', 'action': 'remove'})
            
            if 'pkgs_to_remove' in node['policies'][str(packages_policy['_id'])]:
                del node['policies'][str(packages_policy['_id'])]['pkgs_to_remove']
                
            node['policies'][str(packages_policy['_id'])]['package_list'] = package_list
            
            # Update policies
            self.db.nodes.update({'_id': node['_id']}, {'$set': {'policies': node['policies']}})
            logger.debug('Joined list: %s'%(str(node['policies'][str(packages_policy['_id'])]['package_list'])))


        # Recalculate policies
        for node_id in updated_nodes:
            node = self.db.nodes.find_one({"_id": ObjectId(node_id)})
            if node is None:
                logger.error('FATAL: Can\'t find node with ID: %s'%(node_id))
                return                
            
            # Chef if this node was already updated because its path
            already_updated = False
            for obj_id in node['path'].split(','):
                if obj_id in updated_nodes:
                    already_updated = True
            
            if already_updated:
                logger.info("Node %s already updated because of its path"%(node_id))
                
            else:
                logger.info("Updating Node %s"%(node_id))
                if node['type'] == 'ou':
                    logger.info('Applying policies to OU')
                    apply_policies_to_ou(self.db.nodes, node, self.auth_user, api=self.api)
                if node['type'] == 'group':
                    logger.info('Applying policies to GROUP')
                    apply_policies_to_group(self.db.nodes, node, self.auth_user, api=self.api)
                if node['type'] == 'computer':
                    logger.info('Applying policies to COMPUTER')
                    apply_policies_to_computer(self.db.nodes, node, self.auth_user, api=self.api)            
            
        logger.info('%s nodes were updated!'%(len(updated_nodes)))
        
        # Final check
        bad_nodes = Search('node', "pkgs_to_remove:*", rows=1000, start=0, api=self.api)
        for node in bad_nodes:
            logger.warn('Detected bad node: %s'%(node.object.name))
            gecos_node = self.db.nodes.find_one({"chef_node_id": node.object.name})
            if gecos_node is None:
                logger.warn('Can\'t find node in MongoDB for: %s'%(node.object.name)) 
            else:
                logger.warn('For an unknown reason a computer called %s wasn\'t updated!'%(gecos_node['name'])) 
        
        package_nodes = Search('node', "package_res:*", rows=1000, start=0, api=self.api)
        for node in package_nodes:
            logger.info('Checking node: %s'%(node.object.name))
            if not "pkgs_to_remove" in node['default']["gecos_ws_mgmt"]["software_mgmt"]["package_res"]:
                logger.error("Chef node %s contains a pkgs_to_remove value!")
                return
                
            if not "package_list" in node['default']["gecos_ws_mgmt"]["software_mgmt"]["package_res"]:
                logger.error("Chef node %s doesn\'t contains a package_list value!")
                return
            
            package_list = node['default']["gecos_ws_mgmt"]["software_mgmt"]["package_res"]["package_list"]
            bad_element = False
            for element in package_list:
                if not 'action' in element:
                    logger.warn('Chef node: %s doesn\'t have an action value in package_res! (package_list:%s)'%(node.object.name, str(package_list))) 
                    break
        
        logger.info('END ;)')
        
    