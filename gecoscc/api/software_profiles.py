from cornice.resource import resource

from gecoscc.api import ResourcePaginatedReadOnly
from gecoscc.models import SoftwareProfile, SoftwareProfiles
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/software_profiles/',
          path='/api/software_profiles/{oid}/',
          description='SoftwareProfiles resource',
          validators=(api_login_required,))
class SoftwareProfilesResource(ResourcePaginatedReadOnly):

    schema_collection = SoftwareProfiles
    schema_detail = SoftwareProfile
    objtype = 'software_profiles'

    mongo_filter = {}

    collection_name = objtype
