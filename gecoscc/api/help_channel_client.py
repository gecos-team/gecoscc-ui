#
# Copyright 2018, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Abraham Macías <amacias@gruposolutia.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import urllib2
import datetime
import os
import string
import re
import socket
from random import randint, choice
from cornice.resource import resource
from gecoscc.utils import get_chef_api
from chef import ChefError
from chef.exceptions import ChefServerError
from chef import Client as ChefClient
from chef import Node as ChefNode
from Crypto.PublicKey import RSA
from bson import ObjectId

import logging
logger = logging.getLogger(__name__)

known_message = 'En un lugar de la Mancha, de cuyo nombre no quiero acordarme,'\
    ' no ha mucho tiempo que vivía un hidalgo de los de lanza en astillero, '\
    'adarga antigua, rocín flaco y galgo corredor.'




@resource(collection_path='/help-channel-client/',
          path='/help-channel-client/login',
          description='Help Channel client login')
class HelpChannelClientLogin():

    def __init__(self, request):
        self.request = request

    def post(self):
        logger.debug('/help-channel-client/login START') 
        
        # Check the parameters
        node_id = self.request.POST.get('node_id')
        if not node_id:
            logger.error('/help-channel-client/login - No node ID') 
            return {'ok': False,
                    'message': 'Please set a node id'}
            
        username = self.request.POST.get('username')
        if not username:
            logger.error('/help-channel-client/login - No username') 
            return {'ok': False,
                    'message': 'Please set a username'}
            
        secret = self.request.POST.get('secret')
        if not secret:
            logger.error('/help-channel-client/login - No secret') 
            return {'ok': False,
                    'message': 'Please set a secret'}

        hc_server = self.request.POST.get('hc_server')
        if not hc_server:
            logger.error('/help-channel-client/login - No server') 
            return {'ok': False,
                    'message': 'Please set a Help Channel Server'}

        gcc_username = self.request.POST.get('gcc_username')
        if not gcc_username:
            logger.error('/help-channel-client/login - No admin username') 
            return {'ok': False,
                    'message': 'Please set a GCC administrator username'}
        
        self.request.user = self.request.db.adminusers.find_one(
            {'username': gcc_username})
        if not self.request.user:
            return {'ok': False,
               'message': 'The admin user %s does not exists' % gcc_username}

        logger.debug('/help-channel-client/login node_id=%s'%(node_id)) 
        logger.debug('/help-channel-client/login username=%s'%(username)) 
        logger.debug('/help-channel-client/login secret=%s'%(secret)) 
        logger.debug('/help-channel-client/login hc_server=%s'%(hc_server)) 
        logger.debug('/help-channel-client/login gccusername=%s'%(gcc_username)) 

        gcc_node = self.request.db.nodes.find_one({'node_chef_id': node_id})
        if not gcc_node:
            logger.error('/help-channel-client/login - Node not found') 
            return {'ok': False,
                    'message': 'Node not found in database'}   

        gcc_user = self.request.db.nodes.find_one(
            {'type': 'user', 'name': username})
        if not gcc_user:
            logger.error('/help-channel-client/login - User not found') 
            return {'ok': False,
                    'message': 'User not found in database'}   

        try:
            # Check the secret message
            api = get_chef_api(self.request.registry.settings,
                               self.request.user)
            chef_client = ChefClient(node_id, api)
            if not chef_client.exists:
                logger.error('/help-channel-client/login - Client not found') 
                return {'ok': False, 'message': 'This client does not exists'}
            
            chef_node = ChefNode(node_id, api)
            if not chef_node.exists:
                logger.error('/help-channel-client/login - Chef node not found') 
                return {'ok': False, 'message': 'This chef node does not exists'}            
            
            client_certificate = chef_client.certificate
            public_key = RSA.importKey(client_certificate)
            decrypted = public_key.encrypt(secret.decode('hex'), 0)[0]
            
            if decrypted != known_message:
                logger.error('/help-channel-client/login - Bad secret') 
                return {'ok': False, 'message': 'Bad secret'}
            

            # Login successful, generate the token!
            server_address = self.request.registry.settings.get(
                'server_address', 'UNKNOWN')
            
            if server_address == 'UNKNOWN':
                server_address = os.getenv('HOSTNAME', 'UNKNOWN')
                

            # - Token generation
            min_char = 8
            max_char = 12
            allchar = string.ascii_letters + string.digits
            token = ''.join(choice(allchar) for _ in range(
                randint(min_char, max_char)))        
                
            self.request.db.helpchannel.insert(
                {
                    'last_modified': datetime.datetime.utcnow(),
                    'action': 'request',
                    'computer_node_id': node_id,
                    'computer_node_path': gcc_node['path'],
                    'user_node_id': str(gcc_user['_id']),
                    'user_node_path': gcc_user['path'],
                    'adminuser_id': False,
                    'adminuser_ou_managed': False,
                    'adminuser_is_superuser': False,
                    'gecos_cc_server': server_address,
                    'helpchannel_server': hc_server,
                    'token': token
                }
            )
            
            logger.info('/help-channel-client/login - token: %s'%(token)) 
            return {'ok': True, 'token': token}
                
        except (urllib2.URLError, ChefError, ChefServerError):
            pass

        logger.error('/help-channel-client/login - UNKNOWN') 
        return {'ok': False, 'message': 'Unknown error'}
    


@resource(collection_path='/help-channel-client/',
          path='/help-channel-client/fetch',
          description='Help Channel client fetch technician')
class HelpChannelClientFetch():

    def __init__(self, request):
        self.request = request

    def get(self):
        logger.debug('/help-channel-client/fetch START') 
        
        # Check the parameters
        token = self.request.GET.get('connection_code')
        if not token:
            logger.error('/help-channel-client/fetch - No token') 
            return {'ok': False,
                    'message': 'Please set a connection code'}


        hc_data = self.request.db.helpchannel.find_one({'token': token})
        if not hc_data:
            logger.error('/help-channel-client/fetch - Bad token') 
            return {'ok': False,
                    'message': 'Bad connection code'}        
            

        logger.debug('/help-channel-client/fetch token=%s'%(token)) 

        has_tech = False
        tech_name = ''
        if hc_data['adminuser_id']:
            tech = self.request.db.adminusers.find_one(
                {'_id': ObjectId(hc_data['adminuser_id'])})
            if not tech:
                return {'ok': False,
                   'message': ('The admin user %s does not exists' 
                               % hc_data['adminuser_id'])}
            tech_name = tech['username']
            has_tech = True
            
            
        return {'ok': True, 'has_tech': has_tech, 'tech_name': tech_name}
    


@resource(collection_path='/help-channel-client/',
          path='/help-channel-client/accept',
          description='Help Channel client accept technician')
class HelpChannelClientAccept():

    def __init__(self, request):
        self.request = request

    def get(self):
        logger.debug('/help-channel-client/accept START') 
        
        # Check the parameters
        token = self.request.GET.get('connection_code')
        if not token:
            logger.error('/help-channel-client/accept - No token') 
            return {'ok': False,
                    'message': 'Please set a connection code'}


        hc_data = self.request.db.helpchannel.find_one({'token': token})
        if not hc_data:
            logger.error('/help-channel-client/accept - Bad token') 
            return {'ok': False,
                    'message': 'Bad connection code'}        
            

        logger.debug('/help-channel-client/accept token=%s'%(token)) 

        self.request.db.helpchannel.update({
            '_id': hc_data['_id']
        }, {
            '$set': {
                'action': 'accepted'
            }
        }, multi=True)
            
            
        return {'ok': True}


@resource(collection_path='/help-channel-client/',
          path='/help-channel-client/finish',
          description='Help Channel client end connection')
class HelpChannelClientFinish():

    def __init__(self, request):
        self.request = request

    def get(self):
        logger.debug('/help-channel-client/finish START') 
        
        # Check the parameters
        finisher = self.request.GET.get('finisher')
        if not finisher:
            logger.error('/help-channel-client/finish - No finisher') 
            return {'ok': False,
                    'message': 'Please set a connection finisher'}        
        
        token = self.request.GET.get('connection_code')
        if not token:
            logger.error('/help-channel-client/finish - No token') 
            return {'ok': False,
                    'message': 'Please set a connection code'}


        hc_data = self.request.db.helpchannel.find_one({'token': token})
        if not hc_data:
            logger.error('/help-channel-client/finish - Bad token') 
            return {'ok': False,
                    'message': 'Bad connection code'}        
            

        logger.debug('/help-channel-client/finish token=%s'%(token)) 
        logger.debug('/help-channel-client/finish finisher=%s'%(finisher)) 

        self.request.db.helpchannel.update({
            '_id': hc_data['_id']
        }, {
            '$set': {
                'action': 'finished ' + finisher
            }
        }, multi=True)
            
            
        return {'ok': True}



@resource(collection_path='/help-channel-client/',
          path='/help-channel-client/check',
          description='Help Channel client - check a token')
class HelpChannelClientCheck():

    def __init__(self, request):
        self.request = request

    def get(self):
        logger.debug('/help-channel-client/check START') 
        
        # Check the parameters
        token = self.request.GET.get('connection_code')
        if not token:
            logger.error('/help-channel-client/check - No token') 
            return {'ok': False,
                    'message': 'Please set a connection code'}


        hc_data = self.request.db.helpchannel.find_one({'token': token})
        if not hc_data or not hc_data['action'] == 'accepted':
            logger.error('/help-channel-client/check - Bad token') 
            return {'ok': False,
                    'message': 'Bad connection code'}        
            
        logger.debug('/help-channel-client/check token=%s'%(token))
        
        # Help Channel Server authentication by IP address

        # Get the remote address
        remote_addr = self.request.remote_addr
        header = 'remote_addr'
        if 'X-Real-IP' in self.request.headers:
            remote_addr = self.request.headers['X-Real-IP']
            header = 'X-Real-IP'
        if 'X-Forwarded-For' in self.request.headers:
            remote_addr = self.request.headers['X-Forwarded-For']
            header = 'X-Forwarded-For'
        
        logger.debug('/help-channel-client/check token: remote_addr=%s header=%s (%s)'%(remote_addr, header, str(self.request.headers.items())))        
        
        ip_address = re.compile('^[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}\\.[0-9]{1,3}$')
        
        hc_server = hc_data['helpchannel_server']
        if hc_server.startswith('wss://'):
            hc_server = hc_server[len('wss://'):]
            
        if '/' in hc_server:
            hc_server = hc_server[0:hc_server.find('/')]
            
        if ':' in hc_server:
            hc_server = hc_server[0:hc_server.find(':')]

        
        logger.debug('/help-channel-client/check hc_server:%s'%(hc_server))
        if not ip_address.match(hc_server):
            hc_server = socket.gethostbyname(hc_server)
            
        if not ip_address.match(remote_addr):
            remote_addr = socket.gethostbyname(remote_addr)
        
        logger.debug('/help-channel-client/check - (%s == %s ) ???'%(hc_server, remote_addr))
        if hc_server != remote_addr:
            logger.error('/help-channel-client/check - Bad help channel server (%s != %s )'%(hc_server, remote_addr))
            # Must return 'Bad connection code' message or a possible attacker could
            # know that the connection code is correct
            return {'ok': False,
                    'message': 'Bad connection code'}   
            
        return {'ok': True}
