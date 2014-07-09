import pymongo

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
    order_field = [('_id', pymongo.DESCENDING)]

    mongo_filter = {}

    collection_name = objtype

    def get_oid_filter(self, oid):
        return {self.key: oid}

    def get_objects_filter(self):
        filters = super(JobResource, self).get_objects_filter()
        status = self.request.GET.get('status', '')
        if status:
            filters.append({'status': status})
        return filters

    def collection_get(self):
        result = super(JobResource, self).collection_get()
        jobs = result.get('jobs', [])
        for job in jobs:
            node = self.request.db.nodes.find_one(ObjectId(job['objid']))
            if node:
                job.update({
                    'node_name': node.get('name', ''),
                })
        return result
