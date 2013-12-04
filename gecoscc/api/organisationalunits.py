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

    mongo_filter = {
        'type': 'ou',
    }
    collection_name = 'nodes'

    def post_delete(self, obj):
        """This step delete the children nodes"""
        path = obj['path']
        children_path = ','.join([path, str(obj['_id'])])
        self.collection.remove({
            'path': {
                '$regex': '^{0}'.format(children_path)
            }
        })
