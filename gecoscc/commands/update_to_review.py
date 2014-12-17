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

from bson import ObjectId

from gecoscc.management import BaseCommand


class Command(BaseCommand):
    description = """
        Update to review
    """

    def command(self):
        db = self.pyramid.db
        jobs = db.jobs.find()
        for job in jobs:
            objid = job.get('objid', None)
            if not objid:
                continue
            obj = db.nodes.find_one({'_id': ObjectId(objid)})
            if not obj:
                continue
            db.jobs.update({'_id': job['_id']},
                            {'$set': {'objpath': obj['path']}})
