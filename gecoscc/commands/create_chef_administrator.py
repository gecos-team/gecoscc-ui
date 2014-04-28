import os
import random
import string
import sys

from chef.exceptions import ChefServerNotFoundError, ChefServerError
from getpass import getpass
from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.userdb import UserAlreadyExists
from gecoscc.utils import _get_chef_api, create_chef_admin_user


def password_generator(size=8, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))


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
            help=('The user username')
        ),
        make_option(
            '-e', '--email',
            dest='email',
            action='store',
            help=('The email username')
        ),
        make_option(
            '-n', '--noinput',
            dest='noinput',
            action='store_true',
            default=False,
            help=("Don't ask the password")
        ),
        make_option(
            '-a', '--administrator',
            dest='chef_username',
            action='store',
            help=('An existing chef administrator username')
        ),
        make_option(
            '-k', '--key',
            dest='chef_pem',
            action='store',
            help=('The pem file that contains the chef administrator private key')
        ),
    ]

    required_options = (
        'username',
        'email',
        'chef_username',
        'chef_pem',
    )

    def create_chef_admin_user(self, api, username, password):
        data = {'name': username,
                'password': password,
                'admin': True}
        return api.api_request('POST', '/users', data=data)

    def create_root_ou(self):
        data = {'name': 'ou_0',
                'type': 'ou'}
        if self.db.nodes.find_one(data):
            print "OU with name 'ou_0' already exists in mongo"
        else:
            data.update({'extra': '',
                         'path': 'root',
                         'lock': False,
                         'policies': {},
                         'source': 'gecos'})
            self.db.nodes.insert(data)
            print "OU with name 'ou_0' created in mongo"

    def get_pem_for_username(self, username):
        first_boot_media = self.settings.get('firstboot_api.media')
        user_media = os.path.join(first_boot_media, username)
        if not os.path.exists(user_media):
            os.makedirs(user_media)
        return os.path.join(user_media, 'chef_user.pem')

    def command(self):
        api = _get_chef_api(self.settings.get('chef.url'),
                            self.options.chef_username,
                            self.options.chef_pem)
        try:
            api['/users/%s' % self.options.username]
            print "The username %s already exists in the chef sever" % self.options.username
            sys.exit(1)
        except ChefServerNotFoundError:
            pass

        if not self.options.noinput:
            password = None
            for n in range(3):
                print "Insert the new password, the spaces will be stripped"
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
            print "The generated password is: {0}\n".format(password)

        try:
            create_chef_admin_user(api, self.settings, self.options.username, password)
        except ChefServerError, e:
            print "User not created in chef, error was: %s" % e
            sys.exit(1)

        print "User %s created in chef server" % self.options.username

        try:
            self.pyramid.userdb.create_user(
                self.options.username,
                password,
                self.options.email
            )
        except UserAlreadyExists:
            print "The user already exists in mongo"
        else:
            print "User %s created in mongo" % self.options.username

        self.create_root_ou()
