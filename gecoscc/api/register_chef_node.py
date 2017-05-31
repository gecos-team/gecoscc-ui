#
# Copyright 2016, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Abraham Macias <amp_21004@yahoo.es>
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#


from cornice.resource import resource

from pyramid.threadlocal import get_current_registry

from chef import ChefAPI
from chef import Node as ChefNode
from chef import Client as ChefClient

from gecoscc.permissions import http_basic_login_required
from gecoscc.utils import get_chef_api


@resource(path='/register/node/',
          description='Register a chef node',
          validators=http_basic_login_required)
class RegisterChefNode(object):

    def __init__(self, request):
        self.request = request

    def post(self):
        node_id = self.request.POST.get('node_id')
        if node_id is None:
            return {'ok': False, 'message': 'Missing node ID'}

        settings = get_current_registry().settings
        api = get_chef_api(settings, self.request.user)

        # create chef client
        chef_client = ChefClient(node_id, api)
        if chef_client.exists:
            return {'ok': False, 'message': 'This client already exists'}

        chef_client = ChefClient.create(node_id, api)
        
        # Prepare the API for this client
        chef_url = settings.get('chef.url')
        chef_version = settings.get('chef.version')
        chef_ssl_verify = settings.get('chef.ssl.verify')
        if chef_ssl_verify == 'False' or chef_ssl_verify == 'True':
            chef_ssl_verify = bool(chef_ssl_verify)
        api = ChefAPI(chef_url, str(chef_client.private_key), node_id, chef_version, ssl_verify = False)

 
        # create chef node
        chef_node = ChefNode(node_id, api)
        if chef_node.exists:
            return {'ok': False, 'message': 'This node already exists'}
        chef_node.save()

        return {'ok': True, 'message': 'Node and client have been added',
                'client_private_key': chef_client.private_key}

    def delete(self):
        node_id = self.request.GET.get('node_id')
        if node_id is None:
            return {'ok': False, 'message': 'Missing node ID'}
        
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

    def put(self):
        # implements "knife client reregister"
        node_id = self.request.POST.get('node_id')
        if node_id is None:
            return {'ok': False, 'message': 'Missing node ID'}
            
        settings = get_current_registry().settings
        api = get_chef_api(settings, self.request.user)

        # remove current node's client
        chef_client = ChefClient(node_id, api)
        if not chef_client.exists:
            return {'ok': False, 'message': 'This client does not exists'}

        chef_client = ChefClient.rekey(api)

        return {'ok': True, 'message': "Chef node's client has been update",
                'client_private_key': chef_client.private_key}

    def get(self):
        node_id = self.request.GET.get('node_id')
        if node_id is None:
            return {'ok': False, 'message': 'Missing node ID'}
        
        settings = get_current_registry().settings
        api = get_chef_api(settings, self.request.user)

        chef_node = ChefNode(node_id, api)
        if not chef_node.exists:
            return {'ok': False, 'message': 'This node does not exists'}
        else:
            return {'ok': True, 'message': 'This node does exists'}

