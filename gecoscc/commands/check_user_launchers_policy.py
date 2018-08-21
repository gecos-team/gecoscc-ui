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
from chef import Node as ChefNode

from optparse import make_option
from copy import deepcopy

from gecoscc.management import BaseCommand
from gecoscc.tasks import object_changed, object_created
from gecoscc.utils import _get_chef_api, toChefUsername, get_filter_nodes_belonging_ou, delete_dotted

from bson.objectid import ObjectId
from jsonschema import validate
from jsonschema.exceptions import ValidationError

import requests.packages.urllib3

import logging
logger = logging.getLogger()
    
class Command(BaseCommand):
    description = """
       Check 'User Launchers' policy for all the workstations in the database.
       This script must be executed on major policies updates when the changes in the policies structure may
       cause problems if the Chef nodes aren't properly updated.
       
       So, the right way to use the script is:
       1) Import the new policies with the knife command
       2) Run the "import_policies" command.
       3) Run this "check_user_launchers_policy" command.
    """

    usage = "usage: %prog config_uri check_user_launchers_policy --administrator user --key file.pem"

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
        logger.info("MIGRATION SCRIPT FOR USER_LAUNCHERS POLICY")
        logger.info("###############################################")

        # Disabling InsecureRequestWarning Unverified HTTPS request
        requests.packages.urllib3.disable_warnings()

        sanitized = False
        ous = []
        groups = []
        users = []
        self.api = _get_chef_api(self.settings.get('chef.url'),
                            toChefUsername(self.options.chef_username),
                            self.options.chef_pem, False, self.settings.get('chef.version'))

        self.auth_user = self.db.adminusers.find_one({'username': self.options.chef_username})
        if self.auth_user is None:
            logger.error('The administrator user must exist in MongoDB')
            sys.exit(1)

        self.db = self.pyramid.db
        
        # Get local_users (Users) policy
        logger.info('Getting policy schema (user_launchers_res) ...')
        policy   = self.db.policies.find_one({'slug':'user_launchers_res'})
        schema   = policy['schema']
        policyId = policy['_id']
        
        logger.info('schema   = %s'%str(schema))
        logger.debug('policyId = %s'%str(policyId))

        # Searching nodes with the Local Administrators policy
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
            logger.info("node = %s" % str(node))

            logger.info('-----------------------------------------------')
            logger.info('Node name = %s, mongo_id = %s'%(node['name'],str(node['_id'])))
            logger.info('Instance of the policy on the node: %s'%str(instance))
            while True:
                try:
                    validate(instance, schema)
                    break
                except ValidationError as e: 
                     logger.warn('Validation error on instance = %s'%str(e.message))
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
                if   node['type'] == 'ou':
                    ous.append(node)
                elif node['type'] == 'group':
                    groups.append(node)
                elif node['type'] == 'user':
                    users.append(node)

        # We only go through the highest level OUs. 
        # Therefore, we eliminate intermediate OUs and 
        # then do not recalculate the policies
        # for the same node several times.
        for ou in ous:
            parents = [ObjectId(oid) for oid in ou['path'].split(',') if oid != 'root']
            if any(o['_id'] in parents for o in ous):
                ous.remove(ou)

        # Users that are not under an OU or GROUP that have the migrated policy
        for user in users:
            parents = [ObjectId(oid) for oid in user['path'].split(',') if oid != 'root'] 
            if any(o['_id'] in parents for o in ous):
                users.remove(user)
            elif any(user['_id'] in group['members'] for group in groups):
                users.remove(user)

        # Recalculating policies for OU
        for ou in ous: 
            old = deepcopy(ou)
            del old["policies"][str(policyId)]
            object_changed(self.auth_user, 'ou', ou, old)

        # Recalculating policies for GROUP
        for group in groups:
            old = deepcopy(group)
            del old["policies"][str(policyId)]
            object_changed(self.auth_user, 'group', group, old)

        # Recalculating policies for USER
        for user in users:
            old = deepcopy(user)
            del old["policies"][str(policyId)]
            object_changed(self.auth_user, 'user', user, old)

        logger.info('Finished.')


    def sanitize(self, error, instance):
        logger.info('Sanitizing ...')
        logger.debug('error = %s' % str(error))
        logger.info('Error message = %s' % str(error.message))
        logger.debug('instance = %s' % str(instance))
        
        # CASE 1: jsonschema.exceptions.ValidationError: u'codeblocks' is not of type u'object'
        # Failed validating u'type' in schema[u'properties'][u'launchers'][u'items']:
        #     {u'mergeActionField': u'action',
        #      u'mergeIdField': [u'name'],
        #      u'order': [u'name', u'action'],
        #      u'properties': {u'action': {u'enum': [u'add', u'remove'],
        #                                  u'title': u'Action',
        #                                  u'title_es': u'Acci\xf3n',
        #                                  u'type': u'string'},
        #                      u'name': {u'title': u'Name',
        #                                u'title_es': u'Nombre',
        #                                u'type': u'string',
        #                                u'validate': u'desktopfileExtensionValidate'}},
        #      u'required': [u'name', u'action'],
        #      u'type': u'object'}
        #
        #  On instance[u'launchers'][0]:
        #     u'codeblocks'

        
        # error.path: A collections.deque containing the path to the offending element within the instance. 
        #             The deque can be empty if the error happened at the root of the instance.
        # (http://python-jsonschema.readthedocs.io/en/latest/errors/#jsonschema.exceptions.ValidationError.relative_path)
        # Examples:
        # error.path = deque([u'users_list', 1, u'actiontorun'])
        # error.path = deque([u'users_list', 1])

        if "u'launchers' is a required property" in error.message:
            instance['launchers'] = []
        elif "is not of type u'object'" in error.message:
            error.path.rotate(-1)
            index = error.path.popleft()
            logger.debug('index = %s' % str(index))
            desktopfile = instance['launchers'][index]
            logger.debug('desktopfile = %s' % str(desktopfile))
            logger.debug('BEFORE instance = %s' % str(instance))
            instance['launchers'][index]= {'name': desktopfile, 'action': 'add'}
            logger.debug('AFTER instance = %s' % str(instance))
        else:
            logger.error("Exception: = %s" % str(error))
            raise error
