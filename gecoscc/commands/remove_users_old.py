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

from chef import Node as ChefNode
from chef.exceptions import ChefServerNotFoundError, ChefServerError
from optparse import make_option
from copy import deepcopy

from gecoscc.management import BaseCommand
from gecoscc.models import User
from gecoscc.socks import add_computer_to_user
from gecoscc.utils import (_get_chef_api,
                           toChefUsername,
                           delete_dotted,
                           update_computers_of_user,
                           apply_policies_to_user, apply_policies_to_computer, remove_policies_of_computer,
                           get_filter_in_domain)

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)    

class Command(BaseCommand):
    description = """
        Remove ohai_gecos.users_old attribute from chef node.
        Synchronize ohai_gecos.users attribute from chef node with users in mongo database.
    """

    usage = "usage: %prog config_uri remove_users_old --administrator user --key file.pem"

    option_list = [
        make_option(
            '-a', '--administrator',
            dest='chef_username',
            action='store',
            help='An existing administrator username'
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
        from gecoscc.api.chef_status import USERS_OLD, USERS_OHAI
        # Initialization
        self.api = _get_chef_api(self.settings.get('chef.url'),
                            toChefUsername(self.options.chef_username),
                            self.options.chef_pem, False, self.settings.get('chef.version'))

        self.db = self.pyramid.db

        # Check administrator user
        auth_user = self.db.adminusers.find_one({'username': self.options.chef_username})
        if auth_user is None:
            logger.error('The administrator user must exist in MongoDB')
            sys.exit(1)

        # Recorriendo todos los nodos 
        for node_id in ChefNode.list():
            node = ChefNode(node_id, self.api)
            logger.info('Checking node: %s'%(node_id))
            
            try:
                if node.attributes.get_dotted(USERS_OLD):
                    delete_dotted(node.attributes, USERS_OLD)
                    node.save()
            except KeyError:
                logger.warn("Not found attribute: %s"%(USERS_OLD))
            except:
                logger.warn("Problem deleting users_old attribute from node: %s"%(node_id))

            # Updating users list    
            computer = self.db.nodes.find_one({'node_chef_id': node_id, 'type':'computer'})
            if not computer:
                logger.error('This node does not exist (mongodb)')
                continue
 
            chef_node_usernames = set([d['username'] for d in  node.attributes.get_dotted(USERS_OHAI)])
            gcc_node_usernames  = set([d['name'] for d in self.db.nodes.find({
                                       'type':'user',
                                       'computers': {'$in': [computer['_id']]}
                                    },
                                    {'_id':0, 'name':1})
                                 ])


            users_recalculate_policies = []
            users_remove_policies = []

            # Users added/removed ?
            if set.symmetric_difference(chef_node_usernames, gcc_node_usernames):
                logger.info("Users added/removed found.")

                # Add users or vinculate user to computer if already exists
                addusers = set.difference(chef_node_usernames, gcc_node_usernames)
                for add in addusers:
                    logger.info("Added user: %s"%(add))
                    user = self.db.nodes.find_one({'name': add, 'type': 'user', 'path': get_filter_in_domain(computer)})

                    if not user:
                        user_model = User()
                        user = user_model.serialize({'name': add,
                                                     'path': computer.get('path', ''),
                                                     'type': 'user',
                                                     'lock': computer.get('lock', ''),
                                                     'source': computer.get('source', '')})

                        user = update_computers_of_user(self.db, user, self.api)

                        del user['_id']
                        user_id = self.db.nodes.insert(user)
                        user = self.db.nodes.find_one({'_id': user_id})
                        users_recalculate_policies.append(user)

                    else:
                        computers = user.get('computers', [])
                        if computer['_id'] not in computers:
                            computers.append(computer['_id'])
                            self.db.nodes.update({'_id': user['_id']}, {'$set': {'computers': computers}})
                            users_recalculate_policies.append(user)
                            add_computer_to_user(computer['_id'], user['_id'])

                # Removed users
                delusers = set.difference(gcc_node_usernames, chef_node_usernames)
                for delete in delusers:
                    logger.info("Deleted user: %s"%(delete))
                    user = self.db.nodes.find_one({'name': delete,
                                                   'type': 'user',
                                                   'path': get_filter_in_domain(computer)})
                    computers = user['computers'] if user else []
                    if computer['_id'] in computers:
                        users_remove_policies.append(deepcopy(user))
                        computers.remove(computer['_id'])
                        self.db.nodes.update({'_id': user['_id']}, {'$set': {'computers': computers}})

                for user in users_recalculate_policies:
                    apply_policies_to_user(self.db.nodes, user, auth_user)

                for user in users_remove_policies:
                    remove_policies_of_computer(user, computer, auth_user)
