#
# Copyright 2017, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Jose Manuel Rodriguez Caro <jmrodriguez@solutia-it.es>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import sys

from chef import Node as ChefNode

from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.utils import (_get_chef_api, toChefUsername, get_filter_nodes_belonging_ou, delete_dotted, apply_policies_to_computer)
from bson.objectid import ObjectId
from jsonschema import validate
from jsonschema.exceptions import ValidationError

import requests.packages.urllib3

import logging
logger = logging.getLogger()
    
class Command(BaseCommand):
    description = """
       Check 'Files list' policy for all the workstations in the database.
       This script must be executed on major policies updates when the changes in the policies structure may
       cause problems if the Chef nodes aren't properly updated.
       
       So, the right way to use the script is:
       1) Import the new policies with the knife command
       2) Run the "import_policies" command.
       3) Run the "check_node_policies" command.
       4) Run this "check_local_file_policy" command.
    """

    usage = "usage: %prog config_uri check_local_file_policy --administrator user --key file.pem"

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
        logger.info("MIGRATION SCRIPT FOR FILES LIST POLICY")
        logger.info("######################################")

        # Disabling InsecureRequestWarning Unverified HTTPS request
        requests.packages.urllib3.disable_warnings()

        sanitized = False
        computers = set()                 
        self.api = _get_chef_api(self.settings.get('chef.url'),
                            toChefUsername(self.options.chef_username),
                            self.options.chef_pem, False, self.settings.get('chef.version'))

        self.auth_user = self.db.adminusers.find_one({'username': self.options.chef_username})
        if self.auth_user is None:
            logger.error('The administrator user must exist in MongoDB')
            sys.exit(1)

        self.db = self.pyramid.db
        
        # Get local_file (File list) policy
        logger.info('Getting policy schema (local_file_res) ...')
        policy   = self.db.policies.find_one({'slug':'local_file_res'})
        schema   = policy['schema']
        policyId = policy['_id']
        
        logger.info('schema   = %s'%str(schema))
        logger.debug('policyId = %s'%str(policyId))

        # Searching nodes with the File List policy
        # Query Fields of an Embedded Document (Mongo documentation)
        # Example:
        # db.nodes.find({"policies.58c8122a0dfd425b0894d5b6":{$exists:true}})
        logger.info('Searching for nodes with applied policy...')
        field = 'policies.' + str(policyId)
        filters  = {field:{'$exists':True}}
        nodes = self.db.nodes.find(filters)
  
        # Validating data and, where appropiate, fixing
        for node in nodes:
            instance = node['policies'][unicode(policyId)]
            logger.debug("node = %s" % str(node))

            logger.info('-----------------------------------------------')
            logger.info('Node name = %s, mongo_id = %s'%(node['name'],str(node['_id'])))
            logger.info('Instance of the policy on the node: %s'%str(instance))
            while True:
                try:
                    validate(instance, schema)
                    break
                except ValidationError as e:
                     logger.warn('Validation error on instance: instance = %s'%str(instance))
                     logger.warn('Validation error on instance: message error = %s'%str(e.message))
                     # Sanitize instance
                     self.sanitize(e, instance)
                     sanitized = True

            if sanitized:
                # Setting false sanitized for next iteration
                sanitized = False
                logger.info('Sanitized instance of the policy on the node AFTER calling the validate method: %s'%str(instance))

                # Update mongo
                logger.info('Updating instance in database (mongo) ...')
                self.db.nodes.update({'_id': node['_id']},{'$set':{field:instance}})

                logger.info('Recalculating policies in the node.')

                # Affected nodes
                if node['type'] == 'ou':
                    result = list(self.db.nodes.find({'path': get_filter_nodes_belonging_ou(node['_id']),'type': 'computer'},{'_id':1}))
                    logger.info('OU computers = %s'%str(result))
                elif node['type'] == 'group':
                    result = list(self.db.nodes.find({'_id':{'$in':node['members']},'type':'computer'},{'_id':1}))
                    logger.info('GROUP computers = %s'%str(result))
                elif node['type'] == 'computer':
                    result = [node]
                    logger.info('COMPUTER computers = %s'%str(result))

                [computers.add(str(n['_id'])) for n in result]

        for computer in computers:
            logger.info('Applying policies to COMPUTER. For more information, see "gecosccui-celery.log" file')
            computer = self.db.nodes.find_one({'_id': ObjectId(computer)})
            apply_policies_to_computer(self.db.nodes, computer, self.auth_user, api=self.api, initialize=False, use_celery=True)

        # Removing unused attributes (copy_files, delete_files) in chef nodes
        logger.info('\n')
        attrs = ["%s.copy_files" % (policy['path']), "%s.delete_files" % (policy['path'])]
        logger.info('Removing unused attributes %s in chef nodes ...' % attrs)
        logger.info('\n')        
        
        for node_id in ChefNode.list():
            node = ChefNode(node_id, self.api)
            logger.info('Checking node: %s'%(node_id))
            
            for attr in attrs:
                try:
                    if node.attributes.has_dotted(attr):
                        logger.warn("Remove %s attribute!" % attr)
                        delete_dotted(node.attributes, attr)

                    node.save()

                except:
                    logger.warn("Problem deleting attribute %s value from node: %s"%(attr, node_id))
                    logger.warn("You may be trying to delete a default attribute instead normal attribute: %s"%(node_id))

        logger.info('Finished.')

    def sanitize(self, error, instance):
        logger.info('Sanitizing ...')
        logger.debug('error = %s' % str(error))
        logger.info('Error message = %s' % str(error.message))
        logger.debug('instance = %s' % str(instance))
        
        # CASE 1: jsonschema.exceptions.ValidationError: u'localfiles' is a required property
        # Example:  (instance)
        #        {  
        #          u'copy_files':[  
        #            {  
        #              u'group': u'oem',
        #              u'file_orig': u'http://elites.io/changelog.txt',
        #              u'file_dest': u'/tmp/changelog.txt',
        #              u'user': u'oem',
        #              u'overwrite': False,
        #              u'mode': u'600'
        #            }
        #         ],
        #         u'delete_files':[  
        #         ]
        #       }
        
        # CASE 2: jsonschema.exceptions.ValidationError: Additional properties are not allowed (u'copy_files', u'delete_files' were unexpected)
        # Example:  (instance)
        #        {  
        #          u'copy_files':[  
        #            {  
        #              u'group': u'oem',
        #              u'file_orig': u'http://elites.io/changelog.txt',
        #              u'file_dest': u'/tmp/changelog.txt',
        #              u'user': u'oem',
        #              u'overwrite': False,
        #              u'mode': u'600'
        #            }
        #         ],
        #         u'delete_files':[  
        #         ],
        #         localfiles:[]
        #       }
        
        # error.path: A collections.deque containing the path to the offending element within the instance. 
        #             The deque can be empty if the error happened at the root of the instance.
        # (http://python-jsonschema.readthedocs.io/en/latest/errors/#jsonschema.exceptions.ValidationError.relative_path)
        # Examples:
        # error.path = deque([u'users_list', 1, u'actiontorun'])
        # error.path = deque([u'users_list', 1])

        if "u'localfiles' is a required property" in error.message:
             instance['localfiles'] = []
        elif "u'action' is a required property" in error.message:
             pass
        elif "Additional properties are not allowed (u'copy_files', u'delete_files' were unexpected)" in error.message:
        
            for copyfile in instance['copy_files']:
                logger.debug("copyfile: %s" % copyfile)
                
                copyfile['file']   = copyfile['file_orig']
                copyfile['action'] = 'add'
                del copyfile['file_orig']

                logger.debug("copyfile: %s" % copyfile)

                instance['localfiles'].append(copyfile)
                
            for delfile in instance['delete_files']:
                logger.debug("delfile: %s" % delfile)
                
                delfile['file_dest'] = delfile['file']
                delfile['action'] = 'remove'
                del delfile['file']
                
                logger.debug("delfile: %s" % delfile)

                instance['localfiles'].append(delfile)
                
            del instance['copy_files']
            del instance['delete_files']
        else:
            logger.error("Exception: = %s" % str(error))
            raise error
