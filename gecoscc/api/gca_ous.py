from bson import ObjectId

from cornice.resource import resource

from gecoscc.api import BaseAPI
from gecoscc.models import OrganisationalUnit, OrganisationalUnits
from gecoscc.permissions import http_basic_login_required
from gecoscc.utils import get_items_ou_children


@resource(path='/ou/gca/',
          description='Ous public API',
          validators=(http_basic_login_required,))
class GCAOuResource(BaseAPI):

    schema_collection = OrganisationalUnits
    schema_detail = OrganisationalUnit
    objtype = 'ou'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'

    def get(self):
        user = self.request.user
        ou_ids_availables = self.request.user.get('ou_availables', []) or []
        ous = []
        filters = {'type': 'ou',
                   'path': {'$ne': 'root'},
                   }
        q = self.request.GET.get('q', None)
        if q:
            filters['name'] = {'$regex': '^%s.*' % q,
                               '$options': '-i'}
        if ou_ids_availables:
            ou_ids_availables = [ObjectId(ou_id) for ou_id in ou_ids_availables]
            filters['_id'] = {'$in': ou_ids_availables}
            ous_query = self.request.db.nodes.find(filters)
            ous = [(unicode(ou['_id']), ou['name']) for ou in ous_query]
            for ou_ids_available in ou_ids_availables:
                ou_availables_children = get_items_ou_children(ou_ids_available, self.request.db.nodes, 'ou')
                if ou_availables_children:
                    ous += [(ou_children['_id'], ou_children['name']) for ou_children in ou_availables_children]
            ous = list(set(ous))
        elif user.get('is_superuser'):
            ous = [(unicode(ou['_id']), ou['name']) for ou in self.request.db.nodes.find(filters)]
        return {'ous': ous}
