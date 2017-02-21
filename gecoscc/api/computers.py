#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Emilio Sanchez <emilio.sanchez@gmail.com>
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import urllib2

from cornice.resource import resource
from chef import Node as ChefNode
from chef import ChefError
from chef.exceptions import ChefServerError
from gecoscc.utils import get_chef_api


from gecoscc.api import TreeLeafResourcePaginated
from gecoscc.models import Computer, Computers
from gecoscc.permissions import api_login_required
from gecoscc.utils import to_deep_dict


@resource(collection_path='/api/computers/',
          path='/api/computers/{oid}/',
          description='Computers resource',
          validators=(api_login_required,))
class ComputerResource(TreeLeafResourcePaginated):

    schema_collection = Computers
    schema_detail = Computer
    objtype = 'computer'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'

    def get(self):
        result = super(ComputerResource, self).get()
        if not result.get('node_chef_id', None):
            return result
        try:
            api = get_chef_api(self.request.registry.settings, self.request.user)
            computer_node = ChefNode(result['node_chef_id'], api)
            ohai = to_deep_dict(computer_node.attributes)
            cpu = ohai.get('cpu', {}).get('0', {})
            dmi = ohai.get('dmi', {})
            result.update({'ohai': ohai,
                           'users': ','.join([i['username'] for i in ohai.get('ohai_gecos', {}).get('users', [])]),
                           'uptime': ohai.get('uptime', ''),
                           #'gcc_link': ohai.get('gcc_link',True),
                           'ipaddress': ohai.get('ipaddress', ''),
                           'cpu': '%s %s' % (cpu.get('vendor_id', ''), cpu.get('model_name', '')),
                           'product_name': dmi.get('system', {}).get('product_name', ''),
                           'manufacturer': dmi.get('system', {}).get('manufacturer', ''),
                           'ram': ohai.get('memory', {}).get('total', ''),
                           'lsb': ohai.get('lsb', {}),
                           'kernel': ohai.get('kernel', {}),
                           'filesystem': ohai.get('filesystem', {}),
                           })
        except (urllib2.URLError, ChefError, ChefServerError):
            pass
        return result
