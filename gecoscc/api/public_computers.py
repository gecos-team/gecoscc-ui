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

from cornice.resource import resource

from gecoscc.api import BaseAPI
from gecoscc.models import Computer, Computers
from gecoscc.permissions import http_basic_login_required
from gecoscc.permissions import user_nodes_filter


@resource(path='/computers/list/',
          description='Computers public API',
          validators=(http_basic_login_required,))
class ComputerPublicResource(BaseAPI):

    schema_collection = Computers
    schema_detail = Computer
    objtype = 'computer'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'

    def get(self):
        filters = user_nodes_filter(self.request, ou_type='ou_availables')
        filters['type'] = self.objtype
        q = self.request.GET.get('q', None)
        if q:
            filters['name'] = {'$regex': '%s.*' % q,
                               '$options': '-i'}

        computers_query = self.collection.find(filters)
        computers = [{'node_chef_id': comp['node_chef_id'],
                      'name': comp['name']} for comp in computers_query if comp.get('node_chef_id', None)]
        return {'computers': computers}
