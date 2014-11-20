from cornice.resource import resource

from gecoscc.api import ResourcePaginatedReadOnly
from gecoscc.models import Package, Packages
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/packages/',
          path='/api/packages/{oid}/',
          description='Packages resource',
          validators=(api_login_required,))
class PackagesResource(ResourcePaginatedReadOnly):

    schema_collection = Packages
    schema_detail = Package
    objtype = 'packages'

    mongo_filter = {}

    collection_name = objtype
