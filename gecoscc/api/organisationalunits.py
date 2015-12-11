#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Antonio Perez-Aranda <ant30tx@gmail.com>
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from cornice.resource import resource

from gecoscc.api import TreeResourcePaginated
from gecoscc.models import OrganisationalUnit, OrganisationalUnits
from gecoscc.permissions import http_basic_login_required
from gecoscc.utils import is_domain, MASTER_DEFAULT


@resource(collection_path='/api/ous/',
          path='/api/ous/{oid}/',
          description='Organisatinal Units resource',
          validators=(http_basic_login_required,))
class OrganisationalUnitResource(TreeResourcePaginated):

    schema_collection = OrganisationalUnits
    schema_detail = OrganisationalUnit
    objtype = 'ou'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'

    def integrity_validation(self, obj, real_obj=None):
        status = super(OrganisationalUnitResource,
                       self).integrity_validation(obj, real_obj)

        if real_obj is not None and obj['path'] != real_obj['path']:
            status_user = self.request.user.get('is_superuser', False) or self.is_ou_empty(obj)
            status = status and status_user
        return status

    def is_ou_empty(self, obj):
        '''
        Check if the Ou contains any object
        '''
        ou_children = self.collection.find({'path': {'$regex': '.*' + unicode(obj['_id']) + '.*'}}).count()

        if ou_children == 0:
            return True
        else:
            return False

    def post_save(self, obj, old_obj=None):
        """ Check if path has changed to refresh children nodes """
        if (self.request.method == 'PUT' and old_obj and
                obj.get('path') != old_obj.get('path')):
            # The ou path has changed
            new_path = ','.join([obj.get('path'), str(old_obj[self.key])])
            old_path = ','.join([old_obj.get('path'), str(old_obj[self.key])])

            children = self.collection.find({
                'path': {
                    '$regex': '^{0}'.format(old_path)
                }
            })
            for child in children:
                old_child_path = child['path']
                new_child_path = str(old_child_path).replace(old_path,
                                                             new_path)
                self.collection.update({
                    self.key: child[self.key]
                }, {
                    '$set': {
                        'path': new_child_path
                    }
                })
        elif self.request.method == 'POST' and is_domain(obj):
            obj['master'] = MASTER_DEFAULT
            obj['master_policies'] = {}
        return obj
