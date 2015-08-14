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
                            self.options.chef_pem)
        try:
            api['/users/%s' % toChefUsername(self.options.username)]
            print "The username %s already exists in the chef sever" % toChefUsername(self.options.username)
            sys.exit(1)
        except ChefServerNotFoundError:
            pass

        chef_password = self.create_password("Insert the chef password, the spaces will be stripped",
                                             "The generated password to chef server is: {0}")
        try:
            create_chef_admin_user(api, self.settings, toChefUsername(self.options.username), chef_password)
        except ChefServerError, e:
            print "User not created in chef, error was: %s" % e
            sys.exit(1)

        print "User %s created in chef server" % toChefUsername(self.options.username)

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
