import datetime

from bson import ObjectId

from chef import Node
from cornice.resource import resource

from gecoscc.api import BaseAPI
from gecoscc.models import Job
from gecoscc.utils import get_chef_api
from gecoscc.socks import invalidate_jobs

from pyramid.threadlocal import get_current_registry


@resource(path='/chef/status/',
          description='Chef callback API')
class ChefStatusResource(BaseAPI):

    schema_detail = Job
    collection_name = 'jobs'

    def put(self):
        node_id = self.request.POST.get('node_id')
        username = self.request.POST.get('gcc_username')
        if not node_id:
            return {'ok': False,
                    'message': 'Please set a node id (node_id)'}
        if not username:
            return {'ok': False,
                    'message': 'Please set a admin username (gcc_username)'}
        self.request.user = self.request.db.adminusers.find_one({'username': username})
        settings = get_current_registry().settings
        api = get_chef_api(settings, self.request.user)
        node = Node(node_id, api)
        job_status = node.attributes.get('job_status')
        if not job_status:
            return {'ok': True}
        for job_id, job_status in job_status.to_dict().items():
            job = self.collection.find_one({'_id': ObjectId(job_id)})
            if not job:
                continue
            if job_status['status'] == 0:
                self.collection.update({'_id': job['_id']},
                                       {'$set': {'status': 'finished',
                                                 'last_update': datetime.datetime.now()}})
                invalidate_jobs(self.request)
            else:
                self.collection.update({'_id': job['_id']},
                                       {'$set': {'status': 'errors',
                                                 'message': job_status.get('message', 'Error'),
                                                 'last_update': datetime.datetime.now()}})
                invalidate_jobs(self.request)
        node.attributes.set_dotted('job_status', {})
        node.save()
        return {'ok': True}
