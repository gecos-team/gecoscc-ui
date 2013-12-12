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
