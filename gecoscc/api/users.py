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

from builtins import str
from cornice.resource import resource

from bson import ObjectId

from gecoscc.api import TreeLeafResourcePaginated
from gecoscc.models import User, Users
from gecoscc.permissions import api_login_required
from gecoscc.utils import get_inheritance_tree_policies_list


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

    def get(self):
        result = super(UserResource, self).get()
        computers_ids = [ObjectId(c) for c in result.get('computers')]
        node_collection = self.request.db.nodes

        computers = node_collection.find({'_id': {'$in': computers_ids}, 'type': 'computer'})
        computer_names = [computer['name'] for computer in computers]
        
        # Create a list of users that provides at least one user policy to this computer
        computers_inheritance_pre = list(node_collection.find({
            "$and": [
                { "$or": [{"_id": {"$in": computers_ids}}] }, 
                { "type":"computer"}
             ]
        },{'_id':1,'name':1,'path':1, 'inheritance': 1}))
        [d.update({'_id': str(d['_id'])}) for d in computers_inheritance_pre]        
        
        computers_inheritance = []
        for comp_inh in computers_inheritance_pre:
            if 'inheritance' in comp_inh:
                policies_list = get_inheritance_tree_policies_list(comp_inh['inheritance'], [])
                if len(policies_list) > 0:
                    computers_inheritance.append(comp_inh)

        result.update({'computer_names': computer_names,
                'computers_inheritance': computers_inheritance # Computers related with this user that provides at least one user policy
            })
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
