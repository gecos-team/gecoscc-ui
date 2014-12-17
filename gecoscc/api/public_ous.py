#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from pyramid.httpexceptions import HTTPForbidden

from cornice.resource import resource

from gecoscc.api import BaseAPI
from gecoscc.models import OrganisationalUnit, OrganisationalUnits
from gecoscc.permissions import api_login_required
from gecoscc.utils import get_items_ou_children


@resource(path='/ou/list/',
          description='Ous public API',
          validators=(api_login_required,))
class OuPublicResource(BaseAPI):

    schema_collection = OrganisationalUnits
    schema_detail = OrganisationalUnit
    objtype = 'ou'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'

    def get(self):
        if not self.request.user.get('is_superuser'):
            raise HTTPForbidden()
        ou_id = self.request.GET.get('ou_id', None)
        return get_items_ou_children(ou_id, self.collection, self.objtype)
