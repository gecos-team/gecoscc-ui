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

import json
import pymongo

from cornice.resource import resource
from bson import ObjectId

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
        administrator_username = self.request.user['username']
        filters.append({'administrator_username': administrator_username})
        # Only macrojobs
        parentId = self.request.GET.get('parentId', None)
        if parentId:
            filters.append({'parent': ObjectId(parentId)})
        else:
            filters.append({'parent': {'$exists': True, '$eq': None}})
        status = self.request.GET.get('status', '')
        if status:
            filters.append({'status': status})
        archived = self.request.GET.get('archived', '')
        if archived:
            filters.append({'archived': json.loads(archived)})
        return filters
