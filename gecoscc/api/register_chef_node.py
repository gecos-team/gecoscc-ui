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

from pyramid.threadlocal import get_current_registry

from chef import Node as ChefNode
from chef import Client as ChefClient

from gecoscc.api import BaseAPI
from gecoscc.permissions import http_basic_login_required
from gecoscc.utils import get_chef_api


@resource(path='/api/register/node/',
          description='Register chef node',
          validators=http_basic_login_required)
class RegisterChefNode(BaseAPI):

    collection_name = 'nodes'

    def post(self):
        node_id = self.request.POST.get('node_id')

        settings = get_current_registry().settings
        api = get_chef_api(settings, self.request.user)

        # create chef node
        chef_node = ChefNode(node_id, api)
        if chef_node.exists:
            return {'ok': False, 'message': 'This node already exists'}
        chef_node.save()

        # create chef client
        chef_client = ChefClient(node_id, api)
        if chef_node.exists:
            return {'ok': False, 'message': 'This client already exists'}

        chef_client = ChefClient.create(node_id, api)

        return {'ok': True, 'message': 'Node and client have been added',
                'client_private_key': chef_client.private_key}

    def delete(self):
        node_id = self.request.GET.get('node_id')
        settings = get_current_registry().settings
        api = get_chef_api(settings, self.request.user)

        chef_node = ChefNode(node_id, api)
        if not chef_node.exists:
            return {'ok': False, 'message': 'This node does not exists'}
        chef_node.delete()

        chef_client = ChefClient(node_id, api)
        if not chef_client.exists:
            return {'ok': False, 'message': 'This client does not exists'}
        chef_client.delete()

        return {'ok': True, 'message': 'Node and client have been deleted'}
