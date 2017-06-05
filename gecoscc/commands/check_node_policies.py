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
from getpass import getpass
from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.userdb import UserAlreadyExists
from gecoscc.utils import _get_chef_api, create_chef_admin_user, password_generator, toChefUsername
from bson.objectid import ObjectId
from gecoscc.models import Policy


def password_generator(size=8, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)    
    
class Command(BaseCommand):
    description = """
       Check the policies data for all the workstations in the database. 
       This script must be executed on major policies updates when the changes in the policies structure may
       cause problems if the Chef nodes aren't properly updated.
       
       So, the curse of action is:
       1) Import the new policies with the knife command
       2) Run the "import_policies" command.
       3) Run this "check_node_policies" command.
    """

    usage = "usage: %prog config_uri check_node_policies --administrator user --key file.pem"

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

        self.db = self.pyramid.db
        self.referenced_data_type = {}
        self.referenced_data_type['storage_can_view'] = 'storage'
        self.referenced_data_type['repository_can_view'] = 'repository'
        self.referenced_data_type['printer_can_view'] = 'printer'
        
        
        # Get all the policies structures
        logger.info('Getting all the policies structures from database...')
        dbpolicies = self.db.policies.find()
        self.policiesdata = {}
        self.slug_check = {}
        for policy in dbpolicies:
            logger.debug('Addig to dictionary: %s => %s'%(policy['_id'], json.dumps(policy['schema'])))
            self.policiesdata[str(policy['_id'])] = policy
            
            # Check policy slug field (must be unique)
            if policy['slug'] in self.slug_check:
                logger.error("There are more than one policy with '%s' slug!"%(policy['slug']))
            else:
                self.slug_check[policy['slug']] = policy
                
            # Check policy serialization
            try:
                logger.debug('Serialized policy: %s'%(json.dumps(Policy().serialize(policy))))
            except Exception as err:
                logger.error('Policy %s with slug %s can\'t be serialized: %s'%(policy['_id'], policy['slug'], str(err)))
                
        
        logger.info('Checking tree...')
        # Look for the root of the nodes tree
        root_nodes = self.db.nodes.find({"path" : "root"})    
        for root in root_nodes:        
            self.check_node_and_subnodes(root)
        
        logger.info('Checking chef node references...')
        # Check the references to Chef nodes
        computers = self.db.nodes.find({"type" : "computer"})    
        for computer in computers:  
            if "node_chef_id" in computer:
                # Check Chef node
                computer_node = ChefNode(computer['node_chef_id'], self.api)
                logger.info("Computer: %s Chef ID: %s"%(computer['name'], computer['node_chef_id']))
                if not computer_node.exists:
                    logger.error("No Chef node with ID %s!"%(computer['node_chef_id']))
                
            else:
                logger.error("No Chef ID in '%s' computer!"%(computer['name']))

                
        logger.info('Checking MongoDB computer references...')
        # Check the references to computer nodes
        for node_id in ChefNode.list():
            found = False
            computers = self.db.nodes.find({"node_chef_id" : node_id})    
            for computer in computers:   
                found = True
                
            if not found:
                pclabel = "(No OHAI-GECOS data in the node)"
                computer_node = ChefNode(node_id, self.api)
                try:
                    pclabel = "(pclabel = %s)"%( computer_node.attributes.get_dotted('ohai_gecos.pclabel') )
                except KeyError:
                    pass
                        
                logger.error("No computer node for Chef ID: '%s' %s!"%(node_id, pclabel))
        
        
        logger.info('END ;)')
        
    def check_node_and_subnodes(self, node):
        '''
        Check the policies applied to a node and its subnodes
        '''        
        self.check_node(node)
        
        if node['type'] == 'ou':
            subnodes = self.db.nodes.find({"path" : "%s,%s"%(node['path'], node['_id'])}) 
            for subnode in subnodes:
                self.check_node_and_subnodes(subnode)
        
        
    def check_node(self, node):
        '''
        Check the policies applied to a node
        '''        
        logger.info('Checking node: "%s" type:%s path: %s'%(node['name'], node['type'], node['path']))
        
        # Check policies
        if 'policies' in node:
            # Check the policies data
            for policy in node['policies']:
                logger.debug('Checking policy with ID: %s'%(policy))
                if not str(policy) in self.policiesdata:
                    logger.error("Can't find %s policy data en the database!"%(policy))
                else:
                    policydata = self.policiesdata[str(policy)]
                    nodedata = node['policies'][str(policy)]
                    
                    # Emiters policies have a "name" field in the data
                    # Non emiters policies have a "title" field in the data
                    namefield = 'name'
                    if not (namefield in policydata):
                        namefield = 'title'
                    
                    if not ('name' in policydata):
                        logger.critical('Policy with ID: %s doesn\'t have a name nor title!'%(str(policy)))
                        continue;
                        
                      
                    logger.info('Checking node: "%s" Checking policy: "%s"'%(node['name'], policydata[namefield]))
                    if 'DEPRECATED' in policydata[namefield]:
                        logger.warning('Using deprecated policy: %s'%(policydata[namefield]))
                        
                    
                    logger.debug('Node policy data: %s'%(json.dumps(node['policies'][str(policy)])))
                    
                    is_emitter_policy = False
                    emitter_policy_slug = None
                    if "is_emitter_policy" in policydata:
                        is_emitter_policy = policydata["is_emitter_policy"]
                        emitter_policy_slug = policydata["slug"]
                    
                    # Check object
                    self.check_object_property(policydata['schema'], nodedata, None, is_emitter_policy, emitter_policy_slug)
                            
        else:
            logger.debug('No policies in this node.')
        
        # Check referenced nodes
        if node['type'] == 'user':
            # Check computers
            new_id_list = self.check_referenced_nodes(node['computers'], ['computer'], 'computers')
            difference = set(node['computers']).difference(set(new_id_list))
            if len(difference) > 0:
                logger.info('FIX: remove %s references'%(difference))
                self.db.nodes.update({'_id': ObjectId(node['_id'])},{'$set': {'computers': new_id_list}})
            
            # Check memberof
            new_id_list = self.check_referenced_nodes(node['memberof'], ['group'], 'memberof')
            difference = set(node['memberof']).difference(set(new_id_list))
            if len(difference) > 0:
                logger.info('FIX: remove %s references'%(difference))
                self.db.nodes.update({'_id': ObjectId(node['_id'])},{'$set': {'memberof': new_id_list}})
            
            
        if node['type'] == 'computer':
            # Check memberof
            new_id_list = self.check_referenced_nodes(node['memberof'], ['group'], 'memberof')
            difference = set(node['memberof']).difference(set(new_id_list))
            if len(difference) > 0:
                logger.info('FIX: remove %s references'%(difference))
                self.db.nodes.update({'_id': ObjectId(node['_id'])},{'$set': {'memberof': new_id_list}})

            
        if node['type'] == 'group':
            # Check memberof
            new_id_list = self.check_referenced_nodes(node['memberof'], ['group'], 'memberof')
            difference = set(node['memberof']).difference(set(new_id_list))
            if len(difference) > 0:
                logger.info('FIX: remove %s references'%(difference))
                self.db.nodes.update({'_id': ObjectId(node['_id'])},{'$set': {'memberof': new_id_list}})
                
            
            # Check members
            new_id_list = self.check_referenced_nodes(node['members'], ['user', 'computer', 'group'], 'members')
            difference = set(node['members']).difference(set(new_id_list))
            if len(difference) > 0:
                logger.info('FIX: remove %s references'%(difference))
                self.db.nodes.update({'_id': ObjectId(node['_id'])},{'$set': {'members': new_id_list}})

        
        
    def check_referenced_nodes(self, id_list, possible_types, property):
        '''
        Check if the nodes with ID in the id_list exists in the database
        and its types belong to the possible_types list
        '''           
        
        new_id_list = []
        for id in id_list:
            ref_nodes = self.db.nodes.find({ "_id" : id })    
            found = False
            for ref_nodes in ref_nodes:        
                found = True
                logger.debug('Referenced node %s for property %s is a %s node'%(id, property, ref_nodes["type"]))
                if not (ref_nodes["type"] in possible_types):
                    logger.error('Bad data type in referenced node %s for property %s (%s not in %s)'%(id, property, ref_nodes["type"], possible_types))
                
            if not found:
                logger.error('Can\'t find referenced node %s for property %s'%(id, property))                
                continue
                
            new_id_list.append(id)
        
        return new_id_list
        
        
    def check_boolean_property(self, schema, nodedata, property):
        if schema is None:
            raise ValueError('Schema is None!')
            
        if nodedata is None:
            raise ValueError('Nodedata is None!')            
            
        if schema['type'] != 'boolean':
            raise ValueError('Schema doesn\'t represent a boolean!')
            
        if nodedata not in ['true', 'false', 'True', 'False', True, False]:
            logger.error('Bad property value: %s (not a boolean) for property %s'%(nodedata, property))
            
            
    def check_number_property(self, schema, nodedata, property):
        if schema is None:
            raise ValueError('Schema is None!')
            
        if nodedata is None:
            raise ValueError('Nodedata is None!')            
            
        if (schema['type'] != 'number') and (schema['type'] != 'integer'):
            raise ValueError('Schema doesn\'t represent a number!')
            
        if not isinstance( nodedata, ( int, long ) ) and not nodedata.isdigit():
            logger.error('Bad property value: %s (not a number) for property %s'%(nodedata, property))
            
            
    def check_string_property(self, schema, nodedata, property, is_emitter, emitter_policy_slug):
        if schema is None:
            raise ValueError('Schema is None!')
            
        if nodedata is None:
            raise ValueError('Nodedata is None!')            
            
        if schema['type'] != 'string':
            raise ValueError('Schema doesn\'t represent a number!')
            
        if not isinstance(nodedata, (str, unicode)):
            logger.error('Bad property value: %s (not a string) for property %s'%(nodedata, property))
            return
            
        if 'enum' in schema:
            if ( len(schema['enum']) > 0 ) and  not (nodedata in schema['enum']):
                logger.error('Bad property value: %s (not in enumeration %s) for property %s'%(nodedata, schema['enum'], property))
                
        if is_emitter:
            # Check if referenced node exists in database
            if  emitter_policy_slug == 'package_profile_res':
                ref_nodes = self.db.software_profiles.find({"_id" : ObjectId(nodedata)})    
                found = False
                for ref_nodes in ref_nodes:        
                    found = True
                    logger.debug('Referenced node %s for property %s is a %s'%(nodedata, property, 'package_profile'))
            
            else:
                ref_nodes = self.db.nodes.find({"_id" : ObjectId(nodedata)})    
                found = False
                for ref_nodes in ref_nodes:        
                    found = True
                    logger.debug('Referenced node %s for property %s is a %s node'%(nodedata, property, ref_nodes["type"]))
                    if ref_nodes["type"] != self.referenced_data_type[emitter_policy_slug]:
                        logger.error('Bad data type in referenced node %s for property %s (%s != %s)'%(nodedata, property, ref_nodes["type"], self.referenced_data_type[emitter_policy_slug]))
                
            if not found:
                logger.error('Can\'t find referenced node %s for property %s'%(nodedata, property))
            
    def check_object_property(self, schema, nodedata, propertyname, is_emitter, emitter_policy_slug):
        if schema is None:
            raise ValueError('Schema is None!')
            
        if nodedata is None:
            raise ValueError('Nodedata is None!')            
            
        if schema['type'] != 'object':
            raise ValueError('Schema doesn\'t represent a object!')
            
        # Check required properties
        if 'required' in schema:
            for property in schema['required']:
                name = str(property)
                if propertyname is not None:
                    name = "%s.%s"%(propertyname, property)
                logger.debug('\tChecking required property: %s'%(name))
                if str(property) in nodedata:
                    logger.debug('\tRequired property: %s exists in the node data.'%(name))
                else:
                    logger.error('\tRequired property: %s doesn\'t exists in the node data!'%(name))

                    
        # Compare the policy schema and the node data
        for property in schema['properties'].keys():
            type = schema['properties'][str(property)]['type']
            name = str(property)
            if propertyname is not None:
                name = "%s.%s"%(propertyname, property)
            logger.debug('\tChecking property: %s (%s)'%(name, type))
            if not str(property) in nodedata:
                logger.debug('\tNon required property missing: %s'%(name))
                continue;
            
            if type == 'array':
                self.check_array_property(schema['properties'][str(property)], nodedata[str(property)], name, is_emitter, emitter_policy_slug)
                
            elif type == 'string':
                self.check_string_property(schema['properties'][str(property)], nodedata[str(property)], name, is_emitter, emitter_policy_slug)
            
            elif type == 'object':
                self.check_object_property(schema['properties'][str(property)], nodedata[str(property)], name, is_emitter, emitter_policy_slug)
        
            elif (type == 'number') or (type == 'integer'):
                self.check_number_property(schema['properties'][str(property)], nodedata[str(property)], name)

            elif type == 'boolean':
                self.check_boolean_property(schema['properties'][str(property)], nodedata[str(property)], name)

            else:
                logger.error('Unknown property type found: %s'%(type))
            
        # Reverse check
        if isinstance(nodedata, dict):
            for property in nodedata.keys():
                name = str(property)
                if propertyname is not None:
                    name = "%s.%s"%(propertyname, property)
                    
                if not str(property) in schema['properties'].keys():
                    logger.warning('\tProperty in database that doesn\'t exist in schema anymore: %s'%(name))
        else:
            logger.error('\tProperty in database that isn\'t an object: %s'%(name))
        
        
            

    def check_array_property(self, schema, nodedata, propertyname, is_emitter, emitter_policy_slug):
        if schema is None:
            raise ValueError('Schema is None!')
            
        if nodedata is None:
            raise ValueError('Nodedata is None!')            
            
        if schema['type'] != 'array':
            raise ValueError('Schema doesn\'t represent an array!')

        if not isinstance(nodedata, list):
            logger.error('Bad property value: %s (not an array) for property %s'%(nodedata, propertyname))
            return

        if 'minItems' in schema:
            if len(nodedata) < schema['minItems']:
                logger.error('Bad property value: %s (under min items) for property %s'%(nodedata, propertyname))
                return

        type = schema['items']['type']
        count = 0
        for value in nodedata:
            name = '%s[%s]'%(propertyname, count)
            if type == 'array':
                self.check_array_property(schema['items'], value, name, is_emitter, emitter_policy_slug)
                
            elif type == 'string':
                self.check_string_property(schema['items'], value, name, is_emitter, emitter_policy_slug)
            
            elif type == 'object':
                self.check_object_property(schema['items'], value, name, is_emitter, emitter_policy_slug)
        
            elif (type == 'number') or (type == 'integer'):
                self.check_number_property(schema['items'], value, name)

            elif type == 'boolean':
                self.check_boolean_property(schema['items'], value, name)

            else:
                logger.error('Unknown property type found: %s'%(type))
                
            count += 1
