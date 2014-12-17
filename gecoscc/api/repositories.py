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
from gecoscc.models import Repository, Repositories
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/repositories/',
          path='/api/repositories/{oid}/',
          description='Repositories resource',
          validators=(api_login_required,))
class RepositoryResource(PassiveResourcePaginated):

    schema_collection = Repositories
    schema_detail = Repository
    objtype = 'repository'

    mongo_filter = {
        'type': 'repository',
    }
    collection_name = 'nodes'
