#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#   Alejandro Blanco <alejandro.b.e@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from cornice.resource import resource

from gecoscc.api import PassiveResourcePaginated
from gecoscc.models import Storage, Storages
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/storages/',
          path='/api/storages/{oid}/',
          description='Storages resource',
          validators=(api_login_required,))
class StorageResource(PassiveResourcePaginated):

    schema_collection = Storages
    schema_detail = Storage
    objtype = 'storage'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'
