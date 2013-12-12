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

    def modify_group_relations(self, obj, old_obj):
        # Modify parent relation
        if obj.get('memberof', '') != old_obj.get('memberof', ''):

            if old_obj.get('memberof', None) is not None:
                # Remove the relation with old group
                pgid = old_obj['memberof']
                self.collection.update({
                    '_id': pgid
                }, {
                    '$pull': {
                        'groupmembers': pgid
                    }
                }, multi=False)

            if obj.get('memberof', None) is not None:
                # Add the new relation with the new group
                # Remove the relation with old group
                pgid = obj['memberof']
                self.collection.update({
                    '_id': pgid
                }, {
                    '$push': {
                        'groupmembers': pgid
                    }
                }, multi=False)

        # Revise children relation
        newmembers = obj.get('groupmembers', [])
        oldmembers = old_obj.get('groupmembers', [])

        adds = [n for n in newmembers if n not in oldmembers]
        removes = [n for n in oldmembers if n not in newmembers]

        for group_id in removes:
            self.collection.update({
                '_id': group_id
            }, {
                '$pull': {
                    'nodemembers': obj[self.key]
                }
            }, multi=False)

        for group_id in adds:

            # Add newmember to new group
            self.collection.update({
                '_id': group_id
            }, {
                '$push': {
                    'nodemembers': obj[self.key]
                }
            }, multi=False)

    def modify_node_relations(self, obj, old_obj):

        newmembers = obj.get('nodemembers', [])
        oldmembers = old_obj.get('nodemembers', [])

        adds = [n for n in newmembers if n not in oldmembers]
        removes = [n for n in oldmembers if n not in newmembers]

        for node_id in removes:
            self.request.nodes.update({
                '_id': node_id
            }, {
                '$pull': {
                    'memberof': obj[self.key]
                }
            }, multi=False)

        for node_id in adds:

            self.request.nodes.update({
                '_id': node_id
            }, {
                '$push': {
                    'memberof': obj[self.key]
                }
            }, multi=False)

    def post_save(self, obj, old_obj):
        if self.request.method == 'DELETE':
            self.remove_relations(obj)
        else:
            self.modify_node_relations(obj, old_obj)
            self.modify_group_relations(obj, old_obj)

        return super(GroupResource, self).pre_save(obj, old_obj)
