#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Jose Manuel Rodriguez Caro <jmrodriguez@solutia-it.es>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from cornice.resource import resource

from gecoscc.api import ResourcePaginatedReadOnly
from gecoscc.models import Settings, Setting
from gecoscc.permissions import api_login_required


@resource(collection_path='/api/mimetypes/',
          path='/api/mimetypes/{oid}/',
          description='Mimetypes resource',
          validators=(api_login_required,))
class MimestypesResource(ResourcePaginatedReadOnly):

    schema_collection = Settings
    schema_detail = Setting
    objtype = 'settings'

    mongo_filter = {
      'type': 'Mimetypes',
    }

    collection_name = "settings"
    
    def set_name_filter(self, query, key_name='name'):
      pass
      
    def get_objects_filter(self):
      return []

      
    def collection_get(self):
      if 'oids' in self.request.GET:
        oid = self.request.GET['oids'].strip()
        node = {
          "settings": [ 
            { 
              "_id": "NOT USED",
              "type": "Mimetypes", 
              "value": oid,
              "key": "mimetypes"
            }
          ],
           "pages": 1, 
           "pagesize": 30, 
           "page": 1
        }
        return node
      else:
        return super(MimestypesResource, self).collection_get()
    