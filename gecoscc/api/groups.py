from bson import ObjectId

from pyramid.httpexceptions import HTTPBadRequest

from cornice.resource import resource

from gecoscc.api import TreeLeafResourcePaginated
from gecoscc.models import Group, Groups
from gecoscc.permissions import api_login_required
from gecoscc.utils import merge_lists


def groups_oids_filter(params):
    oids = params.get('oids')
    return {
        '$or': [{'_id': ObjectId(oid)} for oid in oids.split(',')]
    }


def make_cycles(collection, group, old_group):
    """ Detect if new_group make cycles before save
         return True if make cycles and otherwise return False.
    """
    # TODO
    return False


@resource(collection_path='/api/groups/',
          path='/api/groups/{oid}/',
          description='Groups resource',
          validators=(api_login_required,))
class GroupResource(TreeLeafResourcePaginated):

    schema_collection = Groups
    schema_detail = Group
    objtype = 'group'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'

    def get_objects_filter(self):
        filters = super(GroupResource, self).get_objects_filter()

        if 'oids' in self.request.GET:
            oid_filters = groups_oids_filter(self.request.GET)
            if oid_filters:
                filters += (oid_filters)

        return filters

    def remove_relations(self, obj):
        # Remove group from any other group or node where is defined

        # Remove group link from nodes
        self.collection.update({
            'memberof': obj[self.key]
        }, {
            '$pull': {
                'memberof': obj[self.key]
            }
        }, multi=True)

        # Remove group link from other groups
        self.collection.update({
            'type': 'group',
            'groupmembers': obj[self.key]
        }, {
            '$pull': {
                'groupmembers': obj[self.key]
            }
        }, multi=True)

        # Remove children groups
        for group_id in obj.get('groupmembers', []):
            group = self.collection.find_one({self.key: group_id})
            self.remove_relations(group)
            self.collection.remove({self.key: group_id})

    def modify_group_relations(self, obj, old_obj):
        if old_obj is None:
            return
        # Modify parent relation
        merge_lists(self.collection, obj, old_obj, 'memberof', 'nodemembers')

    def modify_node_relations(self, obj, old_obj):
        if old_obj is None:
            return
        merge_lists(self.collection, obj, old_obj, 'nodemembers', 'memberof')

    def pre_save(self, obj, old_obj=None):
        if make_cycles(self.collection, obj, old_obj):
            raise HTTPBadRequest('This groups combination can create cycles')

        return obj

    def post_save(self, obj, old_obj=None):
        if self.request.method == 'DELETE':
            self.remove_relations(obj)
        else:
            self.modify_node_relations(obj, old_obj)
            self.modify_group_relations(obj, old_obj)

        return super(GroupResource, self).post_save(obj, old_obj)
