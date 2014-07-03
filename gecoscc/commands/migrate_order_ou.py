import string
import random

from gecoscc.management import BaseCommand
from gecoscc.models import OU_ORDER


def password_generator(size=8, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))


class Command(BaseCommand):

    def command(self):
        ous = self.db.nodes.find({'type': 'ou'})
        for ou in ous:
            self.db.nodes.update({'_id': ou['_id']}, {'$set': {'node_order': OU_ORDER}})