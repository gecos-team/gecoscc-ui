#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Emilio Sanchez <emilio.sanchez@gmail.com>
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import os
import sys
import subprocess

from chef.exceptions import ChefServerNotFoundError, ChefServerError
from getpass import getpass
from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.userdb import UserAlreadyExists
from gecoscc.utils import _get_chef_api, create_chef_admin_user, password_generator, toChefUsername


class Command(BaseCommand):
    description = """
       Create an admin user into the local adminusers database and into the defined chef server.

       If you provide the -n option, a password is generated and printed to the shell.
    """

    usage = "usage: %prog config_uri create_chef_administrator --username user --email user@example.com --administrator user --key file.pem"

    option_list = [
        make_option(
            '-u', '--username',
            dest='username',
            action='store',
            help='The user username'
        ),
        make_option(
            '-e', '--email',
            dest='email',
            action='store',
            help='The email username'
        ),
        make_option(
            '-n', '--noinput',
            dest='noinput',
            action='store_true',
            default=False,
            help="Don't ask the password"
        ),
        make_option(
            '-a', '--administrator',
            dest='chef_username',
            action='store',
            help='An existing chef administrator username'
        ),
        make_option(
            '-k', '--key',
            dest='chef_pem',
            action='store',
            help='The pem file that contains the chef administrator private key'
        ),
        make_option(
            '-s', '--is-superuser',
            dest='is_superuser',
            action='store_true',
            default=False,
            help="is superuser?"
        ),
    ]

    required_options = (
        'username',
        'email',
        'chef_username',
        'chef_pem',
    )

    def get_pem_for_username(self, username):
        first_boot_media = self.settings.get('firstboot_api.media')
        user_media = os.path.join(first_boot_media, toChefUsername(username))
        if not os.path.exists(user_media):
            os.makedirs(user_media)
        return os.path.join(user_media, 'chef_user.pem')

    def create_password(self, msg_input, msg_noinput):
        if not self.options.noinput:
            password = None
            for n in range(3):
                print msg_input
                password_1 = getpass("password [1]: ").strip()
                password_2 = getpass("password [2]: ").strip()
                if password_1 and password_2 and password_1 == password_2:
                    password = password_1
                    break
                else:
                    print "Both passwords doesn't match or any of them is empty\n"
            if not password:
                print "You can't set the password, please retry later"
                sys.exit(1)
        else:
            password = password_generator()
            print msg_noinput.format(password)
        return password

    def command(self):
        api = _get_chef_api(self.settings.get('chef.url'),
                            toChefUsername(self.options.chef_username),
                            self.options.chef_pem, self.settings.get('chef.ssl.verify'), self.settings.get('chef.version'))
        try:
            api['/users/%s' % toChefUsername(self.options.username)]
            print "The username %s already exists in the chef sever" % toChefUsername(self.options.username)
            sys.exit(1)
        except ChefServerNotFoundError:
            pass

        chef_password = self.create_password("Insert the chef password, the spaces will be stripped",
                                             "The generated password to chef server is: {0}")
        try:
            create_chef_admin_user(api, self.settings, toChefUsername(self.options.username), chef_password, self.options.email)
        except ChefServerError, e:
            print "User not created in chef, error was: %s" % e
            sys.exit(1)

        print "User %s created in chef server" % toChefUsername(self.options.username)

        if int(self.settings.get('chef.version').split('.')[0]) >= 12:
            if os.path.isfile('/opt/opscode/bin/chef-server-ctl') is not None:
                # Include the user in the "server-admins" group
                cmd = ['/opt/opscode/bin/chef-server-ctl', 'grant-server-admin-permissions', toChefUsername(self.options.username)]
                if subprocess.call(cmd) != 0:
                    print 'ERROR: error adding the administrator to "server-admins" chef group'        
                    sys.exit(1)
            else:
                # Chef 12 /opt/opscode/bin/chef-server-ctl does not exists in the system
                # This use to be because Chef and GECOS CC are installed in different machines
                print "NOTICE: Please remember to grant server admin permissions to this user by executing the following command in Chef 12 server:"
                print "%s %s %s"%('/opt/opscode/bin/chef-server-ctl', 'grant-server-admin-permissions', toChefUsername(self.options.username))

            
            # Add the user to the default organization
            try:
                data = {"user": toChefUsername(self.options.username)}
                response = api.api_request('POST', '/organizations/default/association_requests', data=data) 
                association_id = response["uri"].split("/")[-1]         

                api.api_request('PUT', '/users/%s/association_requests/%s'%(toChefUsername(self.options.username), association_id),  data={ "response": 'accept' }) 
                
            except ChefServerError, e:
                print "User not added to default organization in chef, error was: %s" % e
                sys.exit(1)
                
            # Add the user to the default organization's admins group
            try:
                admins_group = api['/organizations/default/groups/admins']
                admins_group['users'].append(toChefUsername(self.options.username))
                api.api_request('PUT', '/organizations/default/groups/admins', data={ "groupname": admins_group["groupname"], 
                    "actors": {
                        "users": admins_group['users'],
                        "groups": admins_group["groups"]
                    }
                    })                 
                
            except ChefServerError, e:
                print "User not added to default organization's admins group in chef, error was: %s" % e
                sys.exit(1)                
            
            print "User %s set as administrator in the default organization chef server" % toChefUsername(self.options.username)
            

        gcc_password = self.create_password("Insert the GCC password, the spaces will be stripped",
                                            "The generated password to GCC is: {0}")
        try:
            self.pyramid.userdb.create_user(
                self.options.username,
                gcc_password,
                self.options.email,
                {'is_superuser': self.options.is_superuser}
            )
        except UserAlreadyExists:
            print "The user already exists in mongo"
        else:
            print "User %s created in mongo" % self.options.username
