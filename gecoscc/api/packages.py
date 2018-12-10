#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Alberto Beiztegui <albertobeiz@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

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

    order_field = 'name'

    def collection_get(self):
        if 'package_name' in self.request.GET:
            package_name = self.request.GET['package_name'].strip()
            package = self.collection.find_one({'name': package_name})
            if package is None:
                package = ''
            else:
                package = self.schema_detail().serialize(package)
            
            return package
        else:
            return super(PackagesResource, self).collection_get()
