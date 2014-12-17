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
