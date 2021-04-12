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
        
        # Count micro-jobs and macro-jobs that doesn't have any child
        base_filter = { 'administrator_username': administrator_username, 'archived':False, 'parent': {'$exists': True, '$ne': None} }
        
        processing_filter = base_filter.copy()
        processing_filter['status'] = 'processing'

        finished_filter = base_filter.copy()
        finished_filter['status'] = 'finished'

        errors_filter = base_filter.copy()
        errors_filter['status'] = 'errors'

        nprocessing = self.collection.count_documents(processing_filter)
        nfinished = self.collection.count_documents(finished_filter)
        nerrors = self.collection.count_documents(errors_filter)
        ntotal = self.collection.count_documents(base_filter)
        
        return {'processing': nprocessing,
                'finished': nfinished,
                'errors': nerrors,
                'total': ntotal}
