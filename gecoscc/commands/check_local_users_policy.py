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

import os
import sys
import string
import subprocess

from chef.exceptions import ChefServerNotFoundError, ChefServerError
from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.utils import _get_chef_api, toChefUsername, apply_policies_to_ou, apply_policies_to_group, apply_policies_to_computer
from bson.objectid import ObjectId
from jsonschema import validate
from jsonschema.exceptions import ValidationError

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)    
    
class Command(BaseCommand):
    description = """
       Check Users policy for all the workstations in the database. 
       This script must be executed on major policies updates when the changes in the policies structure may
       cause problems if the Chef nodes aren't properly updated.
       
       So, the right way to use the script is:
       1) Import the new policies with the knife command
       2) Run the "import_policies" command.
       3) Run this "check_local_users_policy" command.
    """

    usage = "usage: %prog config_uri check_local_users_policy --administrator user --key file.pem"

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
        sanitized = False
        self.api = _get_chef_api(self.settings.get('chef.url'),
                            toChefUsername(self.options.chef_username),
                            self.options.chef_pem, False, self.settings.get('chef.version'))

        self.db = self.pyramid.db
        
        # Get local_users (Users) policy
        logger.info('Getting Users (local_users_res) policy ...')
        policy   = self.db.policies.find_one({'name':'Users'})
        schema   = policy['schema']
        policyId = policy['_id']
        
        logger.debug('schema   = %s'%str(schema))
        logger.debug('Id.policy = %s'%str(policyId))

        # Searching nodes with the Users policy
        # Query Fields of an Embedded Document (Mongo documentation)
        # Example:
        # db.nodes.find({"policies.58c8122a0dfd425b0894d5b6":{$exists:true}})
        logger.info('Searching nodes with the Users policy...')
        field = 'policies.' + str(policyId)
        filters  = {field:{'$exists':True}}
        nodes = self.db.nodes.find(filters)
  
        # Validating data and, where appropiate, fixing
        for node in nodes:
            instance = node['policies'][unicode(policyId)]

            logger.info('Node name = %s, _id = %s'%(node['name'],str(node['_id'])))
            logger.info('Instance before validate method: %s'%str(instance))
            while True:
                try:
                    validate(instance, schema)
                    break
                except ValidationError as e: 
                     logger.error('Validation error on instance = %s'%str(e.message))
                     # Sanitize instance
                     self.sanitize(e, instance)
                     sanitized = True

            if sanitized:
                # Setting false sanitized for next iteration
                sanitized = False
                logger.info('Sanitized instance: %s'%str(instance))

                # Update mongo
                self.db.nodes.update({'_id': node['_id']},{'$set':{field:instance}})

                # Recalc policies node
                auth_user = self.db.adminusers.find_one({'username': self.options.chef_username})
                if node['type'] == 'ou':
                    logger.info('Applying policies to OU')
                    apply_policies_to_ou(self.db.nodes, node, auth_user, api=self.api)
                if node['type'] == 'group':
                    logger.info('Applying policies to GROUP')
                    apply_policies_to_group(self.db.nodes, node, auth_user, api=self.api)
                if node['type'] == 'computer':
                    logger.info('Applying policies to COMPUTER')
                    apply_policies_to_computer(self.db.nodes, node, auth_user, api=self.api)
                   
        logger.info('Finished.')

    def sanitize(self, error, instance):
        logger.info('Sanitizing ...')

        # CASE 1: jsonschema.exceptions.ValidationError: u'delete' is not one of [u'add', u'remove']
        # Failed validating u'enum' in schema[u'properties'][u'users_list'][u'items'][u'properties'][u'actiontorun']:
        #    {u'enum': [u'add', u'remove'],
        #     u'title': u'Action',
        #     u'title_es': u'Acci\xf3n',
        #     u'type': u'string'}
        #
        # On instance[u'users_list'][1][u'actiontorun']:
        #    u'delete'

        # CASE 2: jsonschema.exceptions.ValidationError: Additional properties are not allowed ('groups' was unexpected)
        # Failed validating u'additionalProperties' in schema[u'properties'][u'users_list'][u'items']:
        #   {u'additionalProperties': False,
        #    u'mergeActionField': u'actiontorun',
        #    u'mergeIdField': [u'user'],
        #    u'order': [u'actiontorun', u'user', u'password', u'name'],
        #    u'properties': {u'actiontorun': {u'enum': [u'add', u'remove'],
        #                    u'title': u'Action',
        #                    u'title_es': u'Acci\xf3n',
        #                    u'type': u'string'},
        #    u'name': {u'title': u'Full Name',
        #              u'title_es': u'Nombre Completo',
        #              u'type': u'string'},
        #    u'password': {u'title': u'Password',
        #                  u'title_es': u'Contrase\xf1a',
        #                  u'type': u'string'},
        #    u'user': {u'title': u'User',
        #              u'title_es': u'Usuario',
        #              u'type': u'string'}},
        #    u'required': [u'user', u'actiontorun'],
        #    u'type': u'object'}
        #
        # On instance[u'users_list'][1]:
        #   {u'actiontorun': u'remove',
        #    u'groups': [u'grp1'],
        #    u'name': u'Oem',
        #    u'password': u'oem',
        #    u'user': u'oem'}

        
        # error.path: A collections.deque containing the path to the offending element within the instance. 
        #             The deque can be empty if the error happened at the root of the instance.
        # (http://python-jsonschema.readthedocs.io/en/latest/errors/#jsonschema.exceptions.ValidationError.relative_path)
        # Examples:
        # error.path = deque([u'users_list', 1, u'actiontorun'])
        # error.path = deque([u'users_list', 1])
        error.path.rotate(-1)
        index = error.path.popleft()

        if 'groups' in error.message:
            del instance['users_list'][index]['groups']
        elif 'create' in error.message:
            instance['users_list'][index]['actiontorun'] = unicode('add')
        elif 'modify' in error.message:
            instance['users_list'][index]['actiontorun'] = unicode('add')
        elif 'delete' in error.message:
            instance['users_list'][index]['actiontorun'] = unicode('remove')
        else:
            raise error
