from cornice.resource import resource

from gecoscc.api import BaseAPI
from gecoscc.models import Jobs, Job
from gecoscc.permissions import api_login_required


@resource(path='/api/jobs-statistics/',
          description='Jobs statistics',
          validators=(api_login_required,))
class JobStatistics(BaseAPI):

    schema_collection = Jobs
    schema_detail = Job
    objtype = 'jobs'

    mongo_filter = {}

    collection_name = objtype

    def get_oid_filter(self, oid):
        return {self.key: oid}

    def get(self):
        return {'processing': self.collection.find({'status': 'processing'}).count(),
                'finished': self.collection.find({'status': 'finished'}).count(),
                'errors': self.collection.find({'status': 'errors'}).count(),
                'total': self.collection.find().count()}