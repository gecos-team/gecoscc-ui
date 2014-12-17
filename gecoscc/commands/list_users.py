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

import string
import random

from gecoscc.management import BaseCommand


def password_generator(size=8, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))


class Command(BaseCommand):
    description = """
        Create an admin user into the local adminusers database.

        if you provide the -n option, a passwod is generated and printed to the
        shell
    """

    usage = "usage: %prog config_uri "

    def command(self):
        users = self.pyramid.userdb.list_users()

        print "\n"
        for user in users:
            print "User: {username} email: {email}".format(**user)
