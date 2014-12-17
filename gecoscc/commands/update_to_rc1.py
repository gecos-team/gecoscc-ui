#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from gecoscc.management import BaseCommand
from gecoscc.utils import is_domain


class Command(BaseCommand):
    description = """
        Update to the rc1
    """

    def command(self):
        db = self.pyramid.db
        ous = db.nodes.find({'type': 'ou'})
        for ou in ous:
            if is_domain(ou):
                db.nodes.update({'_id': ou['_id']},
                                {'$set': {'master': ou['source'],
                                          'master_policies': {}}})
