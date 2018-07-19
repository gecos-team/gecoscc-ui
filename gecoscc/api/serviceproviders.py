#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Jose Manuel Rodriguez Caro <jmrodriguez@gruposolutia.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from cornice.resource import resource

from gecoscc.api import ResourcePaginatedReadOnly
from gecoscc.models import ServiceProvider, ServiceProviders
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/serviceproviders/',
          path='/api/serviceproviders/{oid}/',
          description='Mobile Broadband providers resource',
          validators=(api_login_required,))
class ServiceProvidersResource(ResourcePaginatedReadOnly):

    schema_collection = ServiceProviders
    schema_detail = ServiceProvider
    objtype = 'serviceproviders'

    mongo_filter = {}

    collection_name = objtype

    order_field = 'name'

    def get_distinct_filter(self, objects):
        if self.request.GET.get('country_list'): 
            objects = objects.distinct('name')
            objects.sort()
            objects = [{'name': m, 'provider': ''} for m in objects]
        return objects

