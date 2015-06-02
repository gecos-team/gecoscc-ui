#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Antonio Perez-Aranda <ant30tx@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from cornice.resource import resource

from bson import ObjectId

from gecoscc.api import TreeLeafResourcePaginated
from gecoscc.models import User, Users
from gecoscc.permissions import api_login_required
from gecoscc.utils import sanitize


@resource(collection_path='/api/users/',
          path='/api/users/{oid}/',
          description='Users resource',
          validators=(api_login_required,))
class UserResource(TreeLeafResourcePaginated):

    schema_collection = Users
    schema_detail = User
    objtype = 'user'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'


    def pre_save(self, obj, old_obj=None):
        if old_obj and 'name' in old_obj:
            old_obj['name'] = sanitize(old_obj['name'])
        if obj and 'name' in obj:
            obj['name'] = sanitize(obj['name'])
        return super(UserResource, self).pre_save(obj, old_obj)

    def get(self):
        result = super(UserResource, self).get()
        computers_ids = [ObjectId(c) for c in result.get('computers')]
        node_collection = self.request.db.nodes

        computers = node_collection.find({'_id': {'$in': computers_ids}, 'type': 'computer'})
        computer_names = [computer['name'] for computer in computers]

        result.update({'computer_names': computer_names})
        return result

    def integrity_validation(self, obj, real_obj=None):
        val = super(UserResource, self).integrity_validation(obj, real_obj=real_obj)
        if self.request.method == 'POST':
            if obj.get('computers', None):
                self.request.errors.add('body', 'object', 'Integrity error')
                val = False
        elif self.request.method == 'PUT':
            new_computers = obj.get('computers', None)
            old_computers = real_obj.get('computers', None)
            if new_computers != old_computers:
                self.request.errors.add('body', 'object', 'Integrity error, please refresh the object and save again')
                val = False
        return val
