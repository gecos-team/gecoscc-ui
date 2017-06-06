#
# Copyright 2013, Junta de Andalucia
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

from chef.exceptions import ChefServerNotFoundError, ChefServerError
from getpass import getpass
from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.userdb import UserAlreadyExists
from gecoscc.utils import _get_chef_api, create_chef_admin_user, password_generator, toChefUsername


def password_generator(size=8, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))

class Command(BaseCommand):
    description = """
       Check the administrators, users, clients and the ACL permissions of Chef and GECOS CC mongo database.
    """

    usage = "usage: %prog config_uri migrate_to_chef12 --administrator user --key file.pem"

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
        api = _get_chef_api(self.settings.get('chef.url'),
                            toChefUsername(self.options.chef_username),
                            self.options.chef_pem, False, self.settings.get('chef.version'))
                            
        print '============ CHECKING ADMINISTRATOR USERS ============='                  
        # Check if all the GECOS CC administrators
        # are properly created in Chef 12
        admin_users = self.pyramid.userdb.list_users()
        for admin_user in admin_users:
            print 'Checking admin user: %s'%(admin_user['username'])
            
            # The email must be unique
            users_with_email = self.pyramid.userdb.list_users({'email': admin_user['email']})
            if users_with_email.count() > 1:
                print "ERROR: more than one user with this email: %s"%(admin_user['email'])

            # Get the Chef user
            chef_user = None
            try:
                chef_user = api['/users/%s' % toChefUsername(admin_user['username'])]
            except ChefServerNotFoundError:
                pass            
                            
            if chef_user is None:
                # No chef user found
                print "WARNING: No Chef user found. We will try to create it!"
                
                chef_password = password_generator()
                try:
                    create_chef_admin_user(api, self.settings, toChefUsername(admin_user['username']), chef_password, admin_user['email'])
                except ChefServerError, e:
                    print "ERROR: User not created in chef, error was: %s" % e
                    print "(Check /opt/opscode/embedded/service/opscode-erchef/log/requests.log* for more info)"
                    sys.exit(1)                
                            
                chef_user = api['/users/%s' % toChefUsername(admin_user['username'])]

            # Check the email of the chef user
            if chef_user['email'] != admin_user['email']:
                print "WARNING: The chef user email and the GECOS CC user email doesn't match!"
                print "Try to change the chef user email!"
                chef_user['email'] = admin_user['email']
                api.api_request('PUT', '/users/%s'%(toChefUsername(admin_user['username'])), data=chef_user)                
            
            # Check if the administrator belongs to the "admins" group in the "default" organization
            admins_group = None
            try:
                admins_group = api['/organizations/default/groups/admins']
            except ChefServerNotFoundError:
                pass             
                
            if not toChefUsername(admin_user['username']) in admins_group['users']:
                print "WARNING: GECOS administrator is not a chef administrator for the default organization. We will try to change this!"
                
                # Check if exists an association request for this user
                assoc_requests = None
                try:
                    assoc_requests = api['/organizations/default/association_requests']
                except ChefServerNotFoundError:
                    pass                    
                
                association_id = None
                for req in assoc_requests:
                    if req["username"] == toChefUsername(admin_user['username']):
                        association_id = req["id"]
                
                if association_id is None:
                    # Set an association request for the user in that organization
                    try:
                        data = {"user": toChefUsername(admin_user['username'])}
                        response = api.api_request('POST', '/organizations/default/association_requests', data=data) 
                        association_id = response["uri"].split("/")[-1]
                    except ChefServerError:
                        # Association already exists?
                        pass                    

                if association_id is not None:
                    # Accept the association request
                    api.api_request('PUT', '/users/%s/association_requests/%s'%(toChefUsername(admin_user['username']), association_id),  data={ "response": 'accept' }) 

                # Add the user to the group
                admins_group['users'].append(toChefUsername(admin_user['username']))
                api.api_request('PUT', '/organizations/default/groups/admins', data={ "groupname": admins_group["groupname"], 
                    "actors": {
                        "users": admins_group['users'],
                        "groups": admins_group["groups"]
                    }
                    }) 
            
        
        # Check if all the clients have permissions over the computer node with the same name (if exists)
        print '============ CHECKING COMPUTERS ============='                  
        computers = self.db.nodes.find({"type" : "computer"})
        for computer in computers:
            print 'Checking computer: %s'%(computer['name'])
            
            # Check if the chef node exists
            chef_node = None
            try:
                chef_node = api['/organizations/default/nodes/%s'%(computer["node_chef_id"])]
            except ChefServerNotFoundError:
                pass              
            
            if chef_node is None:
                print "ERROR: There is no chef node!"
                continue
                
            # Check if the chef client exists
            chef_client = None
            try:
                chef_client = api['/organizations/default/clients/%s'%(computer["node_chef_id"])]
            except ChefServerNotFoundError:
                pass              
            
            if chef_client is None:
                print "ERROR: There is no chef client!"
                continue
                
            # Check the ACL for the node
            acl = None
            try:
                acl = api['/organizations/default/nodes/%s/_acl'%(computer["node_chef_id"])]
            except ChefServerNotFoundError:
                pass              
            
            if acl is None:
                print "ERROR: Can't find the node ACL!"
                continue

            if not computer["node_chef_id"] in acl['create']['actors']:
                print "INFO: Fix create permission"
                acl['create']['actors'].append(computer["node_chef_id"])
                api.api_request('PUT', '/organizations/default/nodes/%s/_acl/create'%(computer["node_chef_id"]), data={'create': acl['create']})                 
                
            if not computer["node_chef_id"] in acl['read']['actors']:
                print "INFO: Fix read permission"
                acl['read']['actors'].append(computer["node_chef_id"])
                api.api_request('PUT', '/organizations/default/nodes/%s/_acl/read'%(computer["node_chef_id"]), data={'read': acl['read']})                 

            if not computer["node_chef_id"] in acl['update']['actors']:
                print "INFO: Fix update permission"
                acl['update']['actors'].append(computer["node_chef_id"])
                api.api_request('PUT', '/organizations/default/nodes/%s/_acl/update'%(computer["node_chef_id"]), data={'update': acl['update']})                 
                
            if not computer["node_chef_id"] in acl['grant']['actors']:
                print "INFO: Fix grant permission"
                acl['grant']['actors'].append(computer["node_chef_id"])
                api.api_request('PUT', '/organizations/default/nodes/%s/_acl/grant'%(computer["node_chef_id"]), data={'grant': acl['grant']})                 

            if not computer["node_chef_id"] in acl['delete']['actors']:
                print "INFO: Fix delete permission"
                acl['delete']['actors'].append(computer["node_chef_id"])
                api.api_request('PUT', '/organizations/default/nodes/%s/_acl/delete'%(computer["node_chef_id"]), data={'delete': acl['delete']})                 

                
            
                
        