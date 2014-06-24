from bson import ObjectId
from cornice.resource import resource

from gecoscc.api import ResourcePaginatedReadOnly
from gecoscc.models import Job, Jobs
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/jobs/',
          path='/api/jobs/{oid}/',
          description='Jobs resource',
          validators=(api_login_required,))
class JobResource(ResourcePaginatedReadOnly):

    schema_collection = Jobs
    schema_detail = Job
    objtype = 'jobs'

    mongo_filter = {}

    collection_name = objtype

    def get_oid_filter(self, oid):
        return {self.key: oid}

    def collection_get(self):
        result = super(JobResource, self).collection_get()
        jobs = result.get('jobs', [])
        jobs.sort(lambda x,y: cmp(x.get('last_update'), y.get('last_update')))
        index = 0
        for job in jobs:
            index += 1
            node = self.request.db.nodes.find_one(ObjectId(job['objid']))
            if node:
                job.update({
                    'node_name': node.get('name', ''),
                    'index': index
                })
        return result
