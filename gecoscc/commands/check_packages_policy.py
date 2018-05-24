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
        old_policy_nodes = self.db.nodes.find({ '$query': {path_to_find: { '$exists': True }}, '$orderby': { "path" : 1 }})
        
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


        logger.info('%s nodes were updated!'%(len(updated_nodes)))
        
        # Recalculate policies for Chef nodes
        for node_id in ChefNode.list():
            node = ChefNode(node_id, self.api)
            logger.info('Checking node: %s'%(node_id))
            must_update = False
            if ("gecos_ws_mgmt" in node.attributes) and ("software_mgmt" in node.attributes["gecos_ws_mgmt"]) and ("package_res" in node.attributes["gecos_ws_mgmt"]["software_mgmt"]):
                if "pkgs_to_remove" in node.attributes["gecos_ws_mgmt"]["software_mgmt"]["package_res"]:
                    logger.debug("Chef node %s contains a pkgs_to_remove value!"%(node_id))
                    # Remove pkgs_to_remove from mongodb node
                    logger.info("Remove 'pkgs_to_remove' attribute!")
                    try:
                        del node.attributes["gecos_ws_mgmt"]["software_mgmt"]["package_res"]["pkgs_to_remove"]
                        node.save()
                    except:
                        logger.warn("Problem deleting pkgs_to_remove value from node: %s"%(node_id))
                    
                if not "package_list" in node.attributes["gecos_ws_mgmt"]["software_mgmt"]["package_res"]:
                    logger.error("Chef node %s doesn\'t contains a package_list value!"%(node_id))
                    continue
                
                package_list = node.attributes["gecos_ws_mgmt"]["software_mgmt"]["package_res"]["package_list"]
                bad_element = False
                for element in package_list:
                    if not 'action' in element:
                        logger.debug('Chef node: %s doesn\'t have an action value in package_res! (package_list:%s)'%(node_id, str(package_list))) 
                        must_update = True
                        break
            
            if must_update:
                # Look for mongodb node
                mnode = self.db.nodes.find_one({"node_chef_id": node_id})
                if mnode is None:
                    logger.error('FATAL: Can\'t find node with Chef ID: %s'%(node_id))
                    continue                
                    
                logger.info('Updating node: %s - %s'%(node_id, mnode['name']))
                apply_policies_to_computer(self.db.nodes, mnode, self.auth_user, api=self.api, initialize=False, use_celery=False)           
                
        
        # Final check
        bad_nodes = Search('node', "pkgs_to_remove:*", rows=1000, start=0, api=self.api)
        for node in bad_nodes:
            logger.warn('Detected bad node: %s'%(node.object.name))
            gecos_node = self.db.nodes.find_one({"node_chef_id": node.object.name})
            if gecos_node is None:
                logger.warn('Can\'t find node in MongoDB for: %s'%(node.object.name)) 
            else:
                logger.warn('For an unknown reason a computer called %s wasn\'t updated!'%(gecos_node['name'])) 
                
        logger.info('END ;)')
        
    