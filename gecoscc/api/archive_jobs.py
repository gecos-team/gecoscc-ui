import json

from cornice.resource import resource

from gecoscc.api import BaseAPI
from gecoscc.permissions import api_login_required


@resource(path='/api/archive_jobs/',
          description='Archive all user jobs',
          validators=(api_login_required,))
class ArchiveJobsResource(BaseAPI):

    collection_name = 'jobs'

    def put(self):
        user_name = self.request.user['username']
        self.collection.update({'administrator_username': user_name, 'archived': False}, {'$set': {'archived': True}}, multi=True)
        return {'ok': self.request.user['username']}
