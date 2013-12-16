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

    collection_name = 'jobs'

    def get_oid_filter(self, oid):
        return {self.key: oid}
