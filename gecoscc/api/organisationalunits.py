from cornice.resource import resource

from gecoscc.api import TreeResourcePaginated
from gecoscc.models import OrganisationalUnit, OrganisationalUnits
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/ous/',
          path='/api/ous/{oid}/',
          description='Organisatinal Units resource',
          validators=(api_login_required,))
class OrganisationalUnitResource(TreeResourcePaginated):

    schema_collection = OrganisationalUnits
    schema_detail = OrganisationalUnit
    objtype = 'ou'

    mongo_filter = {
        'type': 'ou',
    }
    collection_name = 'nodes'

    def integrity_validation(self, obj, real_obj=None):
        status = super(OrganisationalUnitResource,
                       self).integrity_validation(obj, real_obj)
        if status:
            return status

        if (real_obj is not None and obj['path'] != real_obj['path']):
            # Check if the ou is moving to self depth, that is not correct.
            if obj['path'] in real_obj['path']:
                self.request.errors.add(
                    obj[self.key], 'path',
                    "the ou is moving to self depth position, "
                    "that is not allowed")
            return False
        return True

    def post_delete(self, obj, old_obj=None):
        """This step delete the children nodes"""
        path = obj['path']
        children_path = ','.join([path, str(obj[self.key])])
        self.collection.remove({
            'path': {
                '$regex': '^{0}'.format(children_path)
            }
        })
        return obj

    def post_save(self, obj, old_obj=None):
        """ Check if path has changed to refresh children nodes """
        if (self.request.method == 'PUT' and old_obj and
                obj.get('path') != old_obj.get('path')):
            #The ou path has changed
            new_path = ','.join([obj.get('path'), str(old_obj[self.key])])
            old_path = ','.join([old_obj.get('path'), str(old_obj[self.key])])

            children = self.collection.find({
                'path': {
                    '$regex': '^{0}'.format(old_path)
                }
            })
            for child in children:
                old_child_path = child['path']
                new_child_path = str(old_child_path).replace(old_path,
                                                             new_path)
                self.collection.update({
                    self.key: child[self.key]
                }, {
                    '$set': {
                        'path': new_child_path
                    }
                })
        return obj
