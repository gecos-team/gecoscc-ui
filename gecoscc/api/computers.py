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

from pyramid.httpexceptions import HTTPForbidden, HTTPFound
from bson import ObjectId
import pymongo
from cornice.resource import resource
from chef import Node as ChefNode
from chef import ChefError
from chef.exceptions import ChefServerError
from gecoscc.utils import get_chef_api, get_inheritance_tree_policies_list

from gecoscc.api import TreeLeafResourcePaginated
from gecoscc.models import Computer, Computers
from gecoscc.permissions import api_login_required
from gecoscc.utils import to_deep_dict
from gecoscc.i18n import gettext as _

from pyramid.threadlocal import get_current_request

import locale
import datetime
import re
import traceback

import logging
logger = logging.getLogger(__name__)

DEBUG_MODE_ENABLE_ATTR_PATH = 'gecos_ws_mgmt.single_node.debug_mode_res.enable_debug'

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
        node_collection = self.request.db.nodes
        
        if not result.get('node_chef_id', None):
            return result
        
        logger.info("/api/computers/: node_chef_id: %s" % (str(result.get('node_chef_id', None))))

        try:
            api = get_chef_api(self.request.registry.settings, self.request.user)
            computer_node = ChefNode(result['node_chef_id'], api)
            ohai = to_deep_dict(computer_node.attributes)
            nodeid = result.get('_id',None)
            usernames = [i['username'] for i in ohai.get('ohai_gecos', {}).get('users', [])]
            users = list(node_collection.find({
                "$and": [
                    { "$or": [{"name": {"$in": usernames}}] }, 
                    { "type":"user"},
                    { "computers": {"$elemMatch": {"$eq": ObjectId(nodeid)}}}
                 ]
            },{'_id':1,'name':1,'path':1}))
            # ObjectId to string for JSON serialize
            [d.update({'_id': str(d['_id'])}) for d in users]
            
            # Create a list of users that provides at least one user policy to this computer
            users_inheritance_pre = list(node_collection.find({
                "$and": [
                    { "$or": [{"name": {"$in": usernames}}] }, 
                    { "type":"user"},
                    { "computers": {"$elemMatch": {"$eq": ObjectId(nodeid)}}}
                 ]
            },{'_id':1,'name':1,'path':1, 'inheritance': 1}))
            [d.update({'_id': str(d['_id'])}) for d in users_inheritance_pre]

            users_inheritance = []
            for usr_inh in users_inheritance_pre:
                if 'inheritance' in usr_inh:
                    policies_list = get_inheritance_tree_policies_list(usr_inh['inheritance'], [])
                    if len(policies_list) > 0:
                        users_inheritance.append(usr_inh)
            
            
            cpu = ohai.get('cpu', {}).get('0', {})
            dmi = ohai.get('dmi', {})
            
            # debug_mode flag for logs tab
            debug_mode = False
            try:
                debug_mode = computer_node.attributes.get_dotted(DEBUG_MODE_ENABLE_ATTR_PATH)
            except KeyError:
                pass
            
            # Get logs info
            logs_data = node_collection.find_one({"type": "computer", "_id": ObjectId(nodeid)}, {"logs": True})
            logs = {}
            if logs_data is not None and 'logs' in logs_data:
                logs_data = logs_data['logs']
                
                date_format = locale.nl_langinfo(locale.D_T_FMT)
                date = datetime.datetime(*map(int, re.split('[^\d]', logs_data['date'])[:-1]))
                localename = locale.normalize(get_current_request().locale_name+'.UTF-8')
                logger.debug("/api/computers/: localename: %s" % (str(localename)))
                locale.setlocale(locale.LC_TIME, localename)
                logs['date'] = date.strftime(date_format)
                logger.debug("/api/computers/: date: %s" % (str(logs['date'])))
                
                logs['files'] = logs_data['files']
                for filedata in logs_data['files']:
                    # Do not send file contents
                    del filedata['content']
            
            # Get Help Channel info
            help_channel_enabled = True
            helpchannel_data = self.request.db.helpchannel.find(
                {"computer_node_id" : result['node_chef_id']}).sort(
                    [("last_modified", pymongo.DESCENDING)]).limit(6)
            helpchannel = {}
            helpchannel['current'] = None
            helpchannel['last'] = []
            if helpchannel_data is not None:
                c = 0
                for hcdata in helpchannel_data:
                    # Format date
                    date_format = locale.nl_langinfo(locale.D_T_FMT)
                    logger.info("last_modified: {0}".format( hcdata['last_modified']))
                    last_mod = re.split('[^\d]', str(hcdata['last_modified']))
                    logger.info("last_mod: {0}".format(last_mod))

                    date = datetime.datetime(*map(int, last_mod[:-2]))
                    localename = locale.normalize(get_current_request().locale_name+'.UTF-8')
                    logger.debug("/api/computers/: localename: %s" % (str(localename)))
                    locale.setlocale(locale.LC_TIME, localename)
                    hcdata['last_modified'] = date.strftime(date_format)
                    
                    if hcdata['user_node_id']:
                        # Format user
                        user_data = node_collection.find_one({"type": "user", "_id": ObjectId(hcdata['user_node_id'])})
                        if user_data:
                            hcdata['user'] = user_data['name']
                        else:
                            logger.error("User not found: {0}".format(hcdata['user_node_id']))
                    else:
                        hcdata['user'] = ''
                    
                    if hcdata['adminuser_id']:
                        # Format user
                        user_data = self.request.db.adminusers.find_one({"_id": ObjectId(hcdata['adminuser_id'])})
                        if user_data:
                            hcdata['admin'] = user_data['username']
                        else:
                            logger.error("Admin user not found: {0}".format(hcdata['adminuser_id']))
                    else:
                        hcdata['admin'] = ''
                        
                    # Translate status info
                    hcdata['status'] = _('Unknown status')
                    if hcdata['action'] == 'request':
                        hcdata['status'] = _('User is requesting support')
                    elif hcdata['action'] == 'accepted':
                        hcdata['status'] = _('User is requesting support')
                    elif hcdata['action'] == 'finished user':
                        hcdata['status'] = _('Terminated by user')
                    elif hcdata['action'] == 'finished tech':
                        hcdata['status'] = _('Terminated by technician')
                    elif hcdata['action'] == 'finished error':
                        hcdata['status'] = _('Terminated because of a communication error')
                    elif hcdata['action'] == 'giving support':
                        hcdata['status'] = _('The technician is giving support to the user')
                        
                        
                    hcdata['_id'] = str(hcdata['_id'])                
                    
                    if (c==0 and hcdata['action']=='accepted'):
                        helpchannel['current'] = hcdata
                    else:
                        helpchannel['last'].append(hcdata)
                    
                    c = c + 1
           
            
            result.update({'ohai': ohai,
                           'users': users, # Users related with this computer
                           'users_inheritance': users_inheritance, # Users related with this computer that provides at least one user policy
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
                           'debug_mode': debug_mode,
                           'logs': logs,
                           'helpchannel': helpchannel,
                           'help_channel_enabled': help_channel_enabled
                           })
        except (urllib2.URLError, ChefError, ChefServerError):
            logger.error("/api/computers/: error getting data: node_chef_id: %s " % (str(result.get('node_chef_id', None))))
            logger.error(traceback.format_exc())

        return result

    def put(self):
        
        if ('action' in self.request.GET and 
            self.request.GET['action'] == 'refresh_policies'):
            # Refresh policies
            return super(ComputerResource, self).refresh_policies()
        
        else:
            # Save object
            return super(ComputerResource, self).put()
        
        
        
@resource(collection_path='/api/computers/',
          path='/api/computers/support/{oid}/',
          description='Computers resource',
          validators=(api_login_required,))
class ComputerSupportResource(TreeLeafResourcePaginated):

    schema_collection = Computers
    schema_detail = Computer
    objtype = 'computer'

    mongo_filter = {
        'type': objtype,
    }
    collection_name = 'nodes'

    def get(self):
        result = super(ComputerSupportResource, self).get()
        if not result.get('node_chef_id', None):
            return result

        
        helpchannel_data = self.request.db.helpchannel.find(
            {"computer_node_id" : result['node_chef_id']}).sort(
                [("last_modified", pymongo.DESCENDING)]).limit(1)

        if helpchannel_data is None or helpchannel_data.count() <= 0:
            logger.error("/api/computers/support/: There is no support request for this computer!")
            raise HTTPForbidden()

        hcdata = helpchannel_data.next()
        
        if hcdata is None or hcdata['action'] != 'accepted':
            logger.error("/api/computers/support/: There is no support request for this computer!")
            raise HTTPForbidden()
        
        else:
            # Set this user as the technician that gives support
            admin = self.request.user
            logger.debug("user = {0}".format(self.request.user))
            
            ou_managed = False
            if 'ou_managed' in admin:
                ou_managed = admin['ou_managed']

            if 'ou_remote' in admin:
                ou_managed += admin['ou_remote']
                
            is_superuser = False
            if 'is_superuser' in admin:
                is_superuser = admin['is_superuser']
            
            
            self.request.db.helpchannel.update({
                '_id': hcdata['_id']
            }, {
                '$set': {
                    'action': 'giving support',
                    'adminuser_id': str(admin['_id']),
                    'adminuser_ou_managed': ou_managed,
                    'adminuser_is_superuser': is_superuser                    
                }
            }, multi=True)            
            
            # Redirect to suppor NoVNC page
            url = hcdata['helpchannel_server'].replace('wss://', 'https://')
            url = url.replace('/wsServer', '/')
            url = url + '?repeaterID=ID:' + hcdata['token']
            raise HTTPFound(location=url)

