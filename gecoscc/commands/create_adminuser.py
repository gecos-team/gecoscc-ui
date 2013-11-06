import sys
from optparse import make_option
from getpass import getpass
import string
import random

from gecoscc.management import BaseCommand
from gecoscc.userdb import UserAlreadyExists


def password_generator(size=8, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))


class Command(BaseCommand):
    description = """
        Create an admin user into the local adminusers database.

        if you provide the -n option, a passwod is generated and printed to the
        shell
    """

    usage = "usage: %prog config_uri create_adminuser --username user --email user@example.com"

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
    ]

    required_options = (
        'username',
        'email',
    )

    def command(self):
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
            print "The generated password is \n{0}\n".format(password)

        try:
            self.pyramid.userdb.create_user(
                self.options.username,
                password,
                self.options.email
            )
        except UserAlreadyExists:
            print "The user already exists"
        else:
            print "\nThe user was created"
