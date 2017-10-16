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

from bson import ObjectId
from cornice.resource import resource
from chef import Node as ChefNode
from chef import ChefError
from chef.exceptions import ChefServerError
from gecoscc.utils import get_chef_api, get_inheritance_tree_policies_list


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
        node_collection = self.request.db.nodes
        
        if not result.get('node_chef_id', None):
            return result
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
                    policies_list = get_inheritance_tree_policies_list(usr_inh['inheritance'])
                    if len(policies_list) > 0:
                        users_inheritance.append(usr_inh)
            
            
            cpu = ohai.get('cpu', {}).get('0', {})
            dmi = ohai.get('dmi', {})
            
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
                           })
        except (urllib2.URLError, ChefError, ChefServerError):
            pass
        return result
