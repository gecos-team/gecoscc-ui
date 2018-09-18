#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Antonio Perez-Aranda <ant30tx@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import sys
from optparse import make_option
from getpass import getpass

from gecoscc.management import BaseCommand
from gecoscc.userdb import UserDoesNotExist
from gecoscc.utils import password_generator


class Command(BaseCommand):
    description = """
        Change the password to an admin user into the local adminusers
        database.

        if you provide the -n option, a passwod is generated and printed to the
        shell
    """

    usage = "usage: %prog config_uri change_password --username user"

    option_list = [
        make_option(
            '-u', '--username',
            dest='username',
            action='store',
            help='The user username'
        ),
        make_option(
            '-n', '--noinput',
            dest='noinput',
            action='store_true',
            default=False,
            help="Don't ask the password"
        ),
    ]

    required_options = (
        'username',
    )

    def command(self):
        if not self.options.noinput:
            password = None
            for _n in range(3):
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
            self.pyramid.userdb.change_password(
                self.options.username,
                password
            )
        except UserDoesNotExist:
            print "\nThe user does not exist"
        else:
            print "\nThe password was changed"
