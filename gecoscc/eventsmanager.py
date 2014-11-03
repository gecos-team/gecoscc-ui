import logging

from datetime import datetime

from pyramid_sockjs.session import Session

from gecoscc.models import JOB_STATUS

logger = logging.getLogger(__name__)

CHANNELS = {
    'admin': ('admin', ),
}


class JobStorage(object):

    class JobDoesNotExist(Exception):
        pass

    class JobAlreadyExists(Exception):
        pass

    class StatusInvalidException(Exception):
        pass

    class JobOperationForbidden(Exception):
        pass

    def __init__(self, collection, user):
        self.collection = collection
        self.user = user

    def check_permissions(self):
        # TODO
        if self.user is None:
            return False

        return True

    def assert_permissions(self):
        # TODO
        # Raise a forbidden exception is not allowed
        if not self.check_permissions():
            raise self.JobOperationForbidden()

    def create(self, obj=None, op=None, status=None,
               computer=None, policyname=None,
               administrator_username=None,
               message=None):
        if obj is None or op is None or status is None:
            raise ValueError('objid, type and op are required')
        elif status not in JOB_STATUS:
            raise self.StatusInvalidException()
        self.assert_permissions()

        objid = obj['_id']
        objname = obj['name']
        objpath = obj['path']
        objtype = obj['type']

        computer = computer or {}

        computerid = computer['_id']
        computername = computer['name']

        userid = self.user['_id']

        job = {
            'userid': userid,
            'objid': objid,
            'objname': objname,
            'objpath': objpath,
            'type': objtype,
            'op': op,
            'status': status,
            'computerid': computerid,
            'computername': computername,
            'policyname': policyname,
            'administrator_username': administrator_username,
            'created': datetime.utcnow(),
            'last_update': datetime.utcnow(),
        }
        if message:
            job['message'] = message
        return self.collection.insert(job)

    def update_status(self, jobid, status):

        self.assert_permissions()

        job = self.collection.find_one({
            '_id': jobid
        })

        if status not in JOB_STATUS:
            raise self.StatusInvalidException()
        if not job:
            raise self.JobDoesNotExist()

        self.collection.update({
            '_id': jobid,
        }, {
            '$set': {
                'status': status,
                'last_update': datetime.utcnow(),
            }
        })

    def get(self, jobid):

        self.assert_permissions()

        job = self.collection.find_one({
            '_id': jobid
        })

        if not job:
            raise self.JobDoesNotExist()

        return job


def get_jobstorage(request):
    if request.is_logged:
        user = request.user
    else:
        user = None
    return JobStorage(request.db.jobs, user)


class EventsManager(Session):

    def on_open(self):
        pass

    def on_message(self, message):
        pass

    def on_close(self):
        pass
