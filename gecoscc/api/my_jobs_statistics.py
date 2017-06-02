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

from cornice.resource import resource

from gecoscc.api import BaseAPI
from gecoscc.models import Jobs, Job
from gecoscc.permissions import api_login_required


@resource(path='/api/my-jobs-statistics/',
          description='My jobs statistics',
          validators=(api_login_required,))
class MyJobStatistics(BaseAPI):

    schema_collection = Jobs
    schema_detail = Job
    objtype = 'jobs'

    mongo_filter = {}

    collection_name = objtype

    def get_oid_filter(self, oid):
        return {self.key: oid}

    def get(self):
        administrator_username = self.request.user['username']
    
        return {'processing': self.collection.find({'status': 'processing', 'administrator_username': administrator_username, 'archived':False}).count(),
                'finished': self.collection.find({'status': 'finished', 'administrator_username': administrator_username, 'archived':False}).count(),
                'errors': self.collection.find({'status': 'errors', 'administrator_username': administrator_username, 'archived':False}).count(),
                'total': self.collection.find({'administrator_username': administrator_username, 'archived':False}).count()}
