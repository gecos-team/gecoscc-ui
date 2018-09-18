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

import json
import requests
import re
from copy import deepcopy

from chef.exceptions import ChefServerNotFoundError
from chef import Node as ChefNode
from optparse import make_option
from distutils.version import LooseVersion

from gecoscc.management import BaseCommand
from gecoscc.utils import (_get_chef_api, toChefUsername, 
                           trace_inheritance, order_groups_by_depth)
from gecoscc.rules import get_username_chef_format
from bson.objectid import ObjectId
from gecoscc.models import Policy

import logging
logger = logging.getLogger()    
    
class Command(BaseCommand):
    description = """
       Check the policies data for all the workstations in the database. 
       This script must be executed on major policies updates when the changes 
       in the policies structure may
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
        make_option(
            '-i', '--inheritance',
            dest='inheritance',
            action='store_true',
            default=False,
            help='Check inheritance field'
        ),        
        make_option(
            '-c', '--clean-inheritance',
            dest='clean_inheritance',
            action='store_true',
            default=False,
            help='Clean inheritance field (must be used with -i)'
        ),          
        make_option(
            '--clean-variables',
            dest='clean_variables',
            action='store_true',
            default=False,
            help='Clean variables information from Chef nodes'
        ),         
    ]

    required_options = (
        'chef_username',
        'chef_pem',
    )
    
    def get_url(self, url):
        r = requests.get(url, verify=False, timeout=30)
        if r.ok:
            if hasattr(r,'text'):
                return r.text
            else:  
                return r.content                
            
        return None     
    
    def get_chef_url(self, url):
        url = url[url.index('://')+3:]
        url = url[url.index('/'):]
            
        print "url=", url
        data = None
        try:
            data = self.api[url]
        except ChefServerNotFoundError:
            pass              
        
        return data
    
    def get_default_data(self, dotted_keys):
        # Get gecos_ws_mgmt cookbook version
        data = None
        try:
            data = self.api['/organizations/default/cookbooks/gecos_ws_mgmt']
        except ChefServerNotFoundError:
            pass              
        
        if (data is None) or (not "gecos_ws_mgmt" in data) or (not "versions" in data["gecos_ws_mgmt"]):
            logger.error('Can\'t get version for gecos_ws_mgmt cookbook!')
            return None
            
        last_version_number = ''
        last_version_url = ''
        for ver in data["gecos_ws_mgmt"]["versions"]:
            if last_version_number == '':
                last_version_number = ver['version']
                last_version_url = ver['url']
            elif  LooseVersion(last_version_number) < LooseVersion(ver['version']):
                last_version_number = ver['version']
                last_version_url = ver['url']
            
        if last_version_number == '':
            logger.error('Can\'t find last version number!')
            return None
            
        logger.info("Cookbook version: %s"%(last_version_number))
        data = self.get_chef_url(last_version_url)
        if data is None:
            logger.error('Can\'t get data for gecos_ws_mgmt cookbook!')
            return None

        if not "attributes" in data:
            logger.error('gecos_ws_mgmt cookbook data doesn\'t contain attributes!')
            return None

        default_attr_url = ''
        for attr in data["attributes"]:
            if attr["name"] == "default.rb" and attr["path"] == "attributes/default.rb":
                default_attr_url = attr["url"] 
                
        if default_attr_url == '':
            logger.error('Can\'t find default attributes file!')
            return None
            
        data = self.get_url(default_attr_url)
        if data is None:
            logger.error('Can\'t download default attributes file!')
            return None

        # Join splited lines        
        previous_line = ''
        new_data = ''
        for line in data.split('\n'):
            if line.strip() != '' and not line.strip().startswith('#'):
                if line.startswith('  '):
                    previous_line = str(previous_line) + str(line.strip())
                else:
                    new_data += previous_line + "\n"
                    previous_line = line.strip()        
        
        data = new_data
        
        # Convert to python
        data = re.sub('\[:(?P<name>[a-zA-Z0-9_]+)\]', '["\g<name>"]', data)
        data = data.replace('true', 'True').replace('false', 'False')
        data = data.replace('true', 'True').replace('.freeze', '')
        
        # Create dictionaries
        created = []
        header = ''
        for line in data.split('\n'):
            # Line example: 
            #   default["gecos_ws_mgmt"]["misc_mgmt"]["chef_conf_res"]["support_os"] = ["GECOS V3", "GECOS V2", "Gecos V2 Lite", "GECOS V3 Lite"]
            if line.strip() != '':
                asignation = line.split('=')
                # Left example:
                #   default["gecos_ws_mgmt"]["misc_mgmt"]["chef_conf_res"]["support_os"]
                left = asignation[0].strip()
                right = asignation[1].strip()
                
                # Save as dotted_key => value
                dotted_key = left.replace('"', '').replace('default[', '').replace('][', '.').replace(']','')
                dotted_keys[dotted_key] = eval(right)
                
                # Create empty dictionaries code
                begining = 0
                position = 0
                if '[' in left:
                    position = left.index('[', begining)
                    while position > 0:
                        variable = left[0:position]
                        begining = position + 1
                        try:
                            position = left.index('[', begining)
                        except ValueError:
                            # String not found
                            position = -1
                            
                        if (not variable in created) and len(variable) != len(left):
                            created.append(variable)
                            header += variable+' = {}\n'
                else:
                    code = compile('%s = %s'%(left, right), '<string>', 'exec')
                    exec code                    
                
        data = header + data
        default = None
        code = compile(data, '<string>', 'exec')
        exec code
        return default
    
    
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
        
        # Get gecos_ws_mgmt cookbook default data structure
        default_data_dotted_keys = {}
        default_data = self.get_default_data(default_data_dotted_keys)
        if default_data is None:
            logger.error("Can't find default data!")
            return
        
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
                logger.warn('Possible cause: New fields in models (Colander) but the import_policies command has not yet been executed to update schema.')
                
        if self.options.clean_inheritance:
            logger.info('Cleaning inheritance field...')
            self.db.nodes.update({"inheritance": { '$exists': True }}, { '$unset': { "inheritance": {'$exist': True } }}, multi=True)
            
        if self.options.clean_variables:
            logger.info('Cleaning variables data from Chef nodes')
            for node_id in ChefNode.list():
                node = ChefNode(node_id, self.api)
                if node.normal.has_dotted('gecos_info'):
                    del node.normal['gecos_info']
                    node.save()                    
            
        
        logger.info('Checking tree...')
        # Look for the root of the nodes tree
        root_nodes = self.db.nodes.find({"path" : "root"})    
        for root in root_nodes:        
            self.check_node_and_subnodes(root)
        
        logger.info('Checking nodes that are outside the tree (missing OUs in the PATH)...')
        # Check node path
        nodes = self.db.nodes.find({})    
        for node in nodes:
            if not 'path' in node:
                logger.error('Node with ID: %s has no "path" attribute!'%(str(node['_id'])))                
                continue

            if not 'name' in node:
                logger.error('Node with ID: %s has no "name" attribute!'%(str(node['_id'])))                
                continue

            if not 'type' in node:
                logger.error('Node with ID: %s has no "type" attribute!'%(str(node['_id'])))                
                continue

                
            for ou_id in node['path'].split(','):
                if ou_id == 'root':
                    continue
                    
                ou = self.db.nodes.find_one({ "_id" : ObjectId(ou_id) })    
                if not ou:
                    logger.error('Can\'t find OU %s that belongs to node path (node ID: %s NAME: %s)'%(str(ou_id), str(node['_id']), node['name']))                
                    continue        
        
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

                
        logger.info('Checking MongoDB computer references and deprecated policies...')
        # Check the references to computer nodes
        for node_id in ChefNode.list():
            found = False
            computers = self.db.nodes.find({"node_chef_id" : node_id})    
            for computer in computers:   
                found = True
                
            computer_node = ChefNode(node_id, self.api)
            if not found:
                pclabel = "(No OHAI-GECOS data in the node)"
                try:
                    pclabel = "(pclabel = %s)"%( computer_node.attributes.get_dotted('ohai_gecos.pclabel') )
                except KeyError:
                    pass
                        
                logger.error("No computer node for Chef ID: '%s' %s!"%(node_id, pclabel))
                logger.warn("Possible cause: The node has been deleted in Gecos Control Center but not in Chef server, either because it was in use at that time or for another unknown reason.")
        
            # Check default data for chef node
            if not computer_node.default.to_dict() or not computer_node.attributes.has_dotted('gecos_ws_mgmt'):
                logger.info("FIXED: For an unknown reason Chef node: %s has no default attributes."%(node_id))
                computer_node.default = default_data
                computer_node.save()
                
            # Check "updated_by" field
            attributes = computer_node.normal.to_dict()
            updated, updated_attributes = self.check_updated_by_field(node_id, None, attributes)
            if updated:
                computer_node.normal = updated_attributes
                computer_node.save()
            
            updated, updated_attributes = self.check_chef_node_policies(node_id, None, attributes)
            if updated:
                computer_node.normal = updated_attributes
                computer_node.save()
            
            
        
        logger.info('END ;)')
        
    def check_updated_by_field(self, node_id, key, attributes):
        updated = False
        if isinstance(attributes, dict):
            for attribute in attributes:
                if attribute == 'updated_by':
                    if 'group' in attributes['updated_by']:
                        # Sort groups
                        sorted_groups = order_groups_by_depth(self.db, attributes['updated_by']['group'])
                        if attributes['updated_by']['group'] != sorted_groups:
                            logger.info("Sorting updated_by field for node {0} - {1}!".format(node_id, key)) 
                            attributes['updated_by']['group'] = sorted_groups
                            updated = True
                else:
                    if key is None:
                        k = attribute
                    else:
                        k = key+'.'+attribute
                        
                    up, attributes[attribute] = self.check_updated_by_field(node_id, k, attributes[attribute])
                    updated = (updated or up)
        
        return updated, attributes
        
    def check_chef_node_policies(self, node_id, key, attributes):
        updated = False
        if 'gecos_ws_mgmt' in attributes:
            to_delete = []
            for group in attributes['gecos_ws_mgmt']:
                for policy_slug in attributes['gecos_ws_mgmt'][group]:
                    if policy_slug not in self.slug_check:
                        logger.warn("Unknown policy slug %s found in node %s."%(policy_slug, node_id))
                        logger.info("FIXED: Remove %s policy information from node %s."%(policy_slug, node_id))
                        to_delete.append('%s.%s'%(group, policy_slug))
                        
            for policy in to_delete:
                group, slug = policy.split('.')
                del attributes['gecos_ws_mgmt'][group][slug]
                updated = True
        
        return updated, attributes
        
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
        
        if self.options.inheritance:
            inheritance_node = deepcopy(node)      
        
        # Check policies
        if 'policies' in node:
            to_remove = []
            # Check the policies data
            for policy in node['policies']:
                logger.debug('Checking policy with ID: %s'%(policy))
                if not str(policy) in self.policiesdata:
                    logger.warn("Can't find %s policy data in the database! (probably deprecated)"%(policy))
                    to_remove.append(str(policy))
                    
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
                    
                    if self.options.inheritance:
                        # Check inheritance field
                        trace_inheritance(logger, self.db, 'change', inheritance_node, deepcopy(policydata))

            changed = False
            for policy in to_remove:
                logger.info("FIXED: Remove %s policy information"%(policy))
                del node['policies'][str(policy)]
                changed = True
                
            if changed:
                self.db.nodes.update({'_id': ObjectId(node['_id'])},{'$set': {'policies': node['policies']}})

                            
        else:
            logger.debug('No policies in this node.')
        
        if self.options.inheritance and ('inheritance' in inheritance_node) and (
            (not 'inheritance' in node) or (inheritance_node['inheritance'] != node['inheritance'])):
            
            # Save inheritance field
            logger.info('FIXED: updating inheritance field!')
            self.db.nodes.update({'_id': ObjectId(node['_id'])},{'$set': {'inheritance': inheritance_node['inheritance']}})
        
        # Check referenced nodes
        if node['type'] == 'user':
            # Check computers
            new_id_list = self.check_referenced_nodes(node['computers'], ['computer'], 'computers')
            difference = set(node['computers']).difference(set(new_id_list))
            if len(difference) > 0:
                logger.info('FIXED: remove %s references'%(difference))
                self.db.nodes.update({'_id': ObjectId(node['_id'])},{'$set': {'computers': new_id_list}})
            
            # Check user data
            self.check_user_data(node)
            
            # Check memberof
            new_id_list = self.check_referenced_nodes(node['memberof'], ['group'], 'memberof')
            difference = set(node['memberof']).difference(set(new_id_list))
            if len(difference) > 0:
                logger.info('FIXED: remove %s references'%(difference))
                self.db.nodes.update({'_id': ObjectId(node['_id'])},{'$set': {'memberof': new_id_list}})
            
            
        if node['type'] == 'computer':
            # Check memberof
            new_id_list = self.check_referenced_nodes(node['memberof'], ['group'], 'memberof')
            difference = set(node['memberof']).difference(set(new_id_list))
            if len(difference) > 0:
                logger.info('FIXED: remove %s references'%(difference))
                self.db.nodes.update({'_id': ObjectId(node['_id'])},{'$set': {'memberof': new_id_list}})

            
        if node['type'] == 'group':
            # Check memberof
            new_id_list = self.check_referenced_nodes(node['memberof'], ['group'], 'memberof')
            difference = set(node['memberof']).difference(set(new_id_list))
            if len(difference) > 0:
                logger.info('FIXED: remove %s references'%(difference))
                self.db.nodes.update({'_id': ObjectId(node['_id'])},{'$set': {'memberof': new_id_list}})
                
            
            # Check members
            new_id_list = self.check_referenced_nodes(node['members'], ['user', 'computer', 'group'], 'members')
            difference = set(node['members']).difference(set(new_id_list))
            if len(difference) > 0:
                logger.info('FIXED: remove %s references'%(difference))
                self.db.nodes.update({'_id': ObjectId(node['_id'])},{'$set': {'members': new_id_list}})
        
    def check_user_data(self, user):
        if user['type'] != 'user':
            raise ValueError('user must be an user')
        
        if ((not 'email' in user or user['email']=='') and
            (not 'first_name' in user or user['first_name']=='') and
            (not 'last_name' in user or user['last_name']=='')):
            
            # Nothing to do
            return
        
        
        computers = self.db.nodes.find_one({ "_id" : ObjectId(user['_id']) })['computers']
        for computer_id in computers:
            computer = self.db.nodes.find_one({ "_id" : ObjectId(computer_id) })
            if "node_chef_id" in computer:
                # Check Chef node
                node = ChefNode(computer['node_chef_id'], self.api)
                logger.info("Computer: %s Chef ID: %s"%(computer['name'], computer['node_chef_id']))
                if not node.exists:
                    logger.error("No Chef node with ID %s!"%(computer['node_chef_id']))
                else:
                    if not node.normal.has_dotted('gecos_info'):
                        node.normal.set_dotted('gecos_info', {})
                        
                    if not node.normal.has_dotted('gecos_info.users'):
                        node.normal.set_dotted('gecos_info.users', {})
                                                
                    username = get_username_chef_format(user)
                    if not node.normal.has_dotted('gecos_info.users.%s'%(username)):
                        node.normal.set_dotted('gecos_info.users.%s'%(username), {})
                        
                    updated = False
                    if (not node.normal.has_dotted('gecos_info.users.%s.email'%(username))
                        or node.normal.get_dotted('gecos_info.users.%s.email'%(username)) != user['email']):
                        node.normal.set_dotted('gecos_info.users.%s.email'%(username), user['email'])
                        updated = True
                        
                    if (not node.normal.has_dotted('gecos_info.users.%s.firstName'%(username))
                        or node.normal.get_dotted('gecos_info.users.%s.firstName'%(username)) != user['first_name']):
                        node.normal.set_dotted('gecos_info.users.%s.firstName'%(username), user['first_name'])
                        updated = True

                    if (not node.normal.has_dotted('gecos_info.users.%s.lastName'%(username))
                        or node.normal.get_dotted('gecos_info.users.%s.lastName'%(username)) != user['last_name']):
                        node.normal.set_dotted('gecos_info.users.%s.lastName'%(username), user['last_name'])
                        updated = True
                        
                    if updated:
                        logger.info("Updating user %s data in computer: %s Chef ID: %s"%(user['name'], computer['name'], computer['node_chef_id']))
                        node.save()         
                
            else:
                logger.error("No Chef ID in '%s' computer!"%(computer['name']))
        
    def check_referenced_nodes(self, id_list, possible_types, property_name):
        '''
        Check if the nodes with ID in the id_list exists in the database
        and its types belong to the possible_types list
        '''           
        
        new_id_list = []
        for node_id in id_list:
            ref_nodes = self.db.nodes.find({ "_id" : node_id })    
            found = False
            for ref_nodes in ref_nodes:        
                found = True
                logger.debug('Referenced node %s for property %s is a %s node'%(node_id, property_name, ref_nodes["type"]))
                if not (ref_nodes["type"] in possible_types):
                    logger.error('Bad data type in referenced node %s for property %s (%s not in %s)'%(node_id, property_name, ref_nodes["type"], possible_types))
                
            if not found:
                logger.error('Can\'t find referenced node %s for property %s'%(node_id, property_name))                
                logger.warn('Possible cause: Unknown. Node references non-existent node in MongoDB.')                
                continue
                
            new_id_list.append(node_id)
        
        return new_id_list
        
        
    def check_boolean_property(self, schema, nodedata, property_name):
        if schema is None:
            raise ValueError('Schema is None!')
            
        if nodedata is None:
            raise ValueError('Nodedata is None!')            
            
        if schema['type'] != 'boolean':
            raise ValueError('Schema doesn\'t represent a boolean!')
            
        if nodedata not in ['true', 'false', 'True', 'False', True, False]:
            logger.error('Bad property value: %s (not a boolean) for property %s'%(nodedata, property_name))
            
            
    def check_number_property(self, schema, nodedata, property_name):
        if schema is None:
            raise ValueError('Schema is None!')
            
        if nodedata is None:
            raise ValueError('Nodedata is None!')            
            
        if (schema['type'] != 'number') and (schema['type'] != 'integer'):
            raise ValueError('Schema doesn\'t represent a number!')
            
        if not isinstance( nodedata, ( int, long ) ) and not nodedata.isdigit():
            logger.error('Bad property value: %s (not a number) for property %s'%(nodedata, property_name))
            
            
    def check_string_property(self, schema, nodedata, property_name, is_emitter, emitter_policy_slug):
        if schema is None:
            raise ValueError('Schema is None!')
            
        if nodedata is None:
            raise ValueError('Nodedata is None!')            
            
        if schema['type'] != 'string':
            raise ValueError('Schema doesn\'t represent a number!')
            
        if not isinstance(nodedata, (str, unicode)):
            logger.error('Bad property value: %s (not a string) for property %s'%(nodedata, property_name))
            return
            
        if 'enum' in schema:
            if ( len(schema['enum']) > 0 ) and  not (nodedata in schema['enum']):
                logger.error('Bad property value: %s (not in enumeration %s) for property %s'%(nodedata, schema['enum'], property_name))
                
        if is_emitter:
            # Check if referenced node exists in database
            ref_nodes = self.db.nodes.find({"_id" : ObjectId(nodedata)})    
            found = False
            for ref_nodes in ref_nodes:        
                found = True
                logger.debug('Referenced node %s for property %s is a %s node'%(nodedata, property_name, ref_nodes["type"]))
                if ref_nodes["type"] != self.referenced_data_type[emitter_policy_slug]:
                    logger.error('Bad data type in referenced node %s for property %s (%s != %s)'%(nodedata, property_name, ref_nodes["type"], self.referenced_data_type[emitter_policy_slug]))
                
            if not found:
                logger.error('Can\'t find referenced node %s for property %s'%(nodedata, property_name))
            
    def check_object_property(self, schema, nodedata, propertyname, is_emitter, emitter_policy_slug):
        if schema is None:
            raise ValueError('Schema is None!')
            
        if nodedata is None:
            raise ValueError('Nodedata is None!')            
            
        if schema['type'] != 'object':
            raise ValueError('Schema doesn\'t represent a object!')
            
        # Check required properties
        if 'required' in schema:
            for req_property in schema['required']:
                name = str(req_property)
                if propertyname is not None:
                    name = "%s.%s"%(propertyname, req_property)
                logger.debug('\tChecking required property: %s'%(name))
                if str(req_property) in nodedata:
                    logger.debug('\tRequired property: %s exists in the node data.'%(name))
                else:
                    logger.error('\tRequired property: %s doesn\'t exists in the node data!'%(name))

                    
        # Compare the policy schema and the node data
        for prop in schema['properties'].keys():
            prop_type = schema['properties'][str(prop)]['type']
            name = str(prop)
            if propertyname is not None:
                name = "%s.%s"%(propertyname, prop)
            logger.debug('\tChecking property: %s (%s)'%(name, prop_type))
            if not str(prop) in nodedata:
                logger.debug('\tNon required property missing: %s'%(name))
                continue;
            
            if prop_type == 'array':
                self.check_array_property(schema['properties'][str(prop)], nodedata[str(prop)], name, is_emitter, emitter_policy_slug)
                
            elif prop_type == 'string':
                self.check_string_property(schema['properties'][str(prop)], nodedata[str(prop)], name, is_emitter, emitter_policy_slug)
            
            elif prop_type == 'object':
                self.check_object_property(schema['properties'][str(prop)], nodedata[str(prop)], name, is_emitter, emitter_policy_slug)
        
            elif (prop_type == 'number') or (prop_type == 'integer'):
                self.check_number_property(schema['properties'][str(prop)], nodedata[str(prop)], name)

            elif prop_type == 'boolean':
                self.check_boolean_property(schema['properties'][str(prop)], nodedata[str(prop)], name)

            else:
                logger.error('Unknown property type found: %s'%(prop_type))
            
        # Reverse check
        if isinstance(nodedata, dict):
            for prop in nodedata.keys():
                name = str(prop)
                if propertyname is not None:
                    name = "%s.%s"%(propertyname, prop)
                    
                if not str(prop) in schema['properties'].keys():
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

        item_type = schema['items']['type']
        count = 0
        for value in nodedata:
            name = '%s[%s]'%(propertyname, count)
            if item_type == 'array':
                self.check_array_property(schema['items'], value, name, is_emitter, emitter_policy_slug)
                
            elif item_type == 'string':
                self.check_string_property(schema['items'], value, name, is_emitter, emitter_policy_slug)
            
            elif item_type == 'object':
                self.check_object_property(schema['items'], value, name, is_emitter, emitter_policy_slug)
        
            elif (item_type == 'number') or (item_type == 'integer'):
                self.check_number_property(schema['items'], value, name)

            elif item_type == 'boolean':
                self.check_boolean_property(schema['items'], value, name)

            else:
                logger.error('Unknown property type found: %s'%(item_type))
                
            count += 1
