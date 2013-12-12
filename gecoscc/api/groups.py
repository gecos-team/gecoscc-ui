from cornice.resource import resource

from gecoscc.api import ResourcePaginated
from gecoscc.models import Group, Groups
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/groups/',
          path='/api/groups/{oid}/',
          description='Groups resource',
          validators=(api_login_required,))
class GroupResource(ResourcePaginated):

    schema_collection = Groups
    schema_detail = Group

    mongo_filter = {}

    collection_name = 'groups'

    def remove_relations(self, obj):
        # Remove group from any other group or node where is defined

        # Remove group link from nodes
        self.request.db.nodes.update({
            'memberof': obj[self.key]
        }, {
            '$pull': {
                'memberof': obj[self.key]
            }
        }, multi=True)

        # Remove group link from other groups
        self.collection.update({
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

    def post_save(self, obj, old_obj):
        if self.request.method == 'DELETE':
            self.remove_relations(obj)

        return super(GroupResource, self).pre_save(obj, old_obj)
