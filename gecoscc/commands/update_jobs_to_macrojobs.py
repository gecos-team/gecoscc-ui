#
# Copyright 2017, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Abraham Macias <amacias@solutia-it.es>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from gecoscc.management import BaseCommand
from gecoscc.utils import is_domain


class Command(BaseCommand):
    description = """
        Update old jobs to the new macrojobs and archivate them.
    """

    def command(self):
        db = self.pyramid.db
        jobs = db.jobs.find({'parent': {'$exists': False}})
        for job in jobs:
            db.jobs.update({'_id': job['_id']}, {'$set': {'parent': None, 'archived': True}})
