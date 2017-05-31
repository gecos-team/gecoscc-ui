#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Antonio Perez-Aranda <ant30tx@gmail.com>
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import logging

from datetime import datetime

from pyramid.threadlocal import get_current_registry

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
               computer=None, policy=None,
               parent=None, childs=0, counter=0,
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

        if policy is None:
            policyname = None
        else:
            policyname = policy.get('name', None)

        computer = computer or {}

        computerid = computer.get('_id', None)
        computername = computer.get('user_and_name', None)
        if not computername:
            computername = computer.get('name', None)

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
            'archived': False,
            'parent': parent,
            'childs': childs,
            'counter': counter
        }
        if policy:
            settings = get_current_registry().settings
            languages = settings.get('pyramid.locales')
            default_locale_name = settings.get('pyramid.default_locale_name')
            for lang in languages:
                if lang == default_locale_name:
                    continue
                job['policyname_%s' % lang] = policy.get('name_%s' % lang)
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
