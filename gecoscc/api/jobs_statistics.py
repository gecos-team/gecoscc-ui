#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

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
        return {
            'processing': self.collection.count_documents(
                {'status': 'processing',
                 'parent': {'$exists': True, '$ne': None}}),
            'finished': self.collection.count_documents(
                {'status': 'finished',
                 'parent': {'$exists': True, '$ne': None}}),
            'errors': self.collection.count_documents(
                {'status': 'errors',
                 'parent': {'$exists': True, '$ne': None}}),
            'total': self.collection.count_documents(
                {'parent': {'$exists': True, '$ne': None}})}
