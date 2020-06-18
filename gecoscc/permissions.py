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

import logging
import socket
from bson import ObjectId

from pyramid.httpexceptions import HTTPForbidden
from pyramid.security import (Allow, Deny, Authenticated, Everyone, ALL_PERMISSIONS,
                              authenticated_userid, forget, remember)


from gecoscc.userdb import UserDoesNotExist
from gecoscc.utils import is_domain, get_domain, is_local_user, MASTER_DEFAULT, RESOURCES_EMITTERS_TYPES

logger = logging.getLogger(__name__)

def is_logged(request):
    return authenticated_userid(request) is not None


def api_login_required(request):
    if not is_logged(request):
        raise HTTPForbidden('Login required')


def http_basic_login_required(request):
    try:
        api_login_required(request)
    except HTTPForbidden, e:
        authorization = request.headers.get('Authorization')
        if not authorization:
            raise e
        username, password = authorization.replace('Basic ', '').decode('base64').split(':')
        try:
            user = request.userdb.login(username, password)
            if not user:
                raise e
        except UserDoesNotExist:
            raise e
        remember(request, username)


def is_path_right(request, path, ou_type='ou_managed'):
    ou_managed_ids = []
    if path is None:
        path = ''

    if isinstance(ou_type, str):
        ou_type = [ou_type]

    for t in ou_type:
        ou_managed_ids += request.user.get(t, [])

    for ou_managed_id in ou_managed_ids:
        if ou_managed_id in path:
            return True
            
    return False


def can_access_to_this_path(request, collection_nodes, oid_or_obj, ou_type='ou_managed'):
    obj = None
    request = request
    ou_managed_ids = request.user.get(ou_type, [])
    if not request.user.get('is_superuser'):
        if not ou_managed_ids:
            logger.error("The user %s has no %s data!"%(request.user.get('username'), ou_type));
            raise HTTPForbidden()
        
        if isinstance(oid_or_obj, dict):
            obj = oid_or_obj
        else:
            obj = collection_nodes.find_one({'_id': ObjectId(oid_or_obj)})
        
        if obj is None:
            logger.error("Unknown object! {0}".format(oid_or_obj));
            raise HTTPForbidden()
            
        path = obj['path']
        if (path == 'root' or len(path.split(',')) == 2) and request.method == 'DELETE':
            logger.warn("Only the superadministrators can delete a domain! (user: %s)"%(request.user.get('username')));
            raise HTTPForbidden()
        
        if '_id' in obj:
            path = '%s,%s' % (path, obj['_id'])
        if not is_path_right(request, path, ou_type):
            if not is_domain(obj) or not request.method == 'GET':
                raise HTTPForbidden()


def is_gecos_master_or_403(request, collection_nodes, obj, schema_detail):
    domain = get_domain(obj, collection_nodes)
    if domain and domain['master'] != MASTER_DEFAULT and not is_local_user(obj, collection_nodes):
        if '_id' not in obj:
            raise HTTPForbidden()
        else:
            mongo_obj = collection_nodes.find_one({'_id': ObjectId(obj['_id'])})
            mongo_obj = schema_detail().serialize(mongo_obj)
            obj = schema_detail().serialize(obj)
            del obj['policies']
            del mongo_obj['policies']
            if obj != mongo_obj:
                raise HTTPForbidden()


def master_policy_no_updated_or_403(request, collection_nodes, obj):
    if obj['type'] in RESOURCES_EMITTERS_TYPES or is_local_user(obj, collection_nodes):
        return
    domain = get_domain(obj, collection_nodes) or {}
    master_policies = domain.get('master_policies', {})
    if master_policies:
        if '_id' in obj:
            mongo_obj = collection_nodes.find_one({'_id': obj['_id']})
        else:
            mongo_obj = {}
        mongo_policies = mongo_obj.get('policies', {})
        policies = obj.get('policies', {})
        for policy_id, _value in master_policies.items():
            if mongo_policies.get(policy_id, None) != policies.get(policy_id, None):
                raise HTTPForbidden()


def nodes_path_filter(request, ou_type='ou_managed'):
    if isinstance(ou_type, str):
        ou_type =[ou_type]

    params = request.GET
    maxdepth = int(params.get('maxdepth', 0))
    path = request.GET.get('path', None)
    range_depth = '0,{0}'.format(maxdepth)
    ou_managed_ids = []
    for t in ou_type:
        ou_managed_ids += request.user.get(t, [])
    if not request.user.get('is_superuser') or ou_managed_ids:
        if path == 'root':
            return {
                '_id': {'$in': [ObjectId(ou_managed_id) for ou_managed_id in ou_managed_ids]}
            }
        elif path is None and ou_managed_ids:
            filters = [
                {
                    'path': {
                        '$regex': '.*%s.*' % '|'.join(ou_managed_ids)
                    }
                }, {
                    '_id': {'$in': [ObjectId(ou_managed_id) for ou_managed_id in ou_managed_ids]}
                }
            ]
            return {'$or': filters}
        elif not is_path_right(request, path, ou_type):
            raise HTTPForbidden()
    elif request.user.get('is_superuser') and path is None:
        return {}
    return {
        'path': {
            '$regex': r'^{0}(,[^,]*){{{1}}}$'.format(path, range_depth),
        }
    }


def user_nodes_filter(request, ou_type='ou_managed'):
    ou_managed_ids = request.user.get(ou_type, [])
    if ou_managed_ids:
        return {'path': {'$regex': '.*%s.*' % '|'.join(ou_managed_ids)}}
    elif request.user.get('is_superuser'):
        return {}
    raise HTTPForbidden()


class RootFactory(object):
    __acl__ = [
        (Allow, Everyone, ALL_PERMISSIONS),
    ]

    def __init__(self, request):
        self.request = request

    def get_groups(self, userid, request):
        return []


class LoggedFactory(object):

    def __acl__(self):
        if self.maintenance and self.maintenance.get('value') is True:
            return [(Allow,'g:maintenance', ALL_PERMISSIONS)]

        return [(Allow, Authenticated, ALL_PERMISSIONS)]
    def __init__(self, request):
        self.request = request
        self.maintenance = self.request.db.settings.find_one({'key':'maintenance_mode'})
        maintenance_msg = self.request.db.settings.find_one({'key':'maintenance_message'})
        if maintenance_msg is not None:
            self.request.session['maintenance_message'] = maintenance_msg.get('value')
        else:
            if 'maintenance_message' in self.request.session:
                del self.request.session['maintenance_message']
        logger.debug("LoggedFactory ::: self.maintenance = %s" % self.maintenance)
        try:
            self.request.user
            logger.debug("LoggedFactory ::: user = %s" % self.request.user)
        except UserDoesNotExist:
            forget(request)

    def get_groups(self, userid, request):
        return []

        
class InternalAccessFactory(object):

    def __acl__(self):
        # Get the remote address
        remote_addr = self.request.remote_addr
        header = 'remote_addr'
        if 'X-Real-IP' in self.request.headers:
            remote_addr = self.request.headers['X-Real-IP']
            header = 'X-Real-IP'
        if 'X-Forwarded-For' in self.request.headers:
            remote_addr = self.request.headers['X-Forwarded-For']
            header = 'X-Forwarded-For'
        
        logger.debug('InternalAccessFactory: remote_addr=%s header=%s (%s)'%(remote_addr, header, str(self.request.headers.items())))
        
        # Check if the remote IP address is localhost
        if remote_addr == '127.0.0.1' or remote_addr == '::1':
            logger.debug('InternalAccessFactory: access allowed for localhost: %s'%(remote_addr))
            remember(self.request, 'localhost_access')
            return  [(Allow, Everyone, 'view')]
        
        server_list = self.request.db.servers.find()
        
        # Check if the remote IP address belongs to a GECOSCC server
        for server in server_list:
            if socket.gethostbyname(server['address']) == remote_addr:
                logger.debug('InternalAccessFactory: access allowed for GECOS CC server: %s'%(server['name']))
                remember(self.request, server['name'])
                return [(Allow, Everyone, 'view')]      
                
        logger.debug('InternalAccessFactory: forbidden access for %s'%(remote_addr))
        raise HTTPForbidden('Internal access only')
        

    def __init__(self, request):
        self.request = request

        

class SuperUserFactory(LoggedFactory):

    def __acl__(self):
        user = self.request.user
        if user:
            is_superuser = user.get('is_superuser')
            if is_superuser:
                return [(Allow, Authenticated, ALL_PERMISSIONS)]
        return [(Allow, Authenticated, [])]


class SuperUserOrMyProfileFactory(LoggedFactory):

    def __acl__(self):
        user = self.request.user
        if user:
            username = self.request.matchdict.get('username') or self.request.GET.get('username')
            is_superuser = user.get('is_superuser')
            if self.maintenance and self.maintenance.get('value') is True:
                return [(Allow,'g:maintenance',ALL_PERMISSIONS)]
            if is_superuser or user.get('username') == username:
                return [(Allow, Authenticated, ALL_PERMISSIONS)]
        return [(Allow, Authenticated, [])]

class ReadOnlyOrManageFactory(LoggedFactory):

    def __acl__(self):
        user = self.request.user
        if user:
            if user.get('is_superuser', False):
                return [(Allow, Authenticated, 'edit'), (Allow, Authenticated, 'is_superuser')]
            if ( user.get('ou_managed', []) or
                 user.get('ou_readonly', [])
            ) :
                return [(Allow, Authenticated, 'edit')]

        return [(Deny, Everyone, [])]

class ManageFactory(LoggedFactory):

    def __acl__(self):
        user = self.request.user
        if user:
            if user.get('is_superuser', False):
                return [(Allow, Authenticated, 'edit'), (Allow, Authenticated, 'is_superuser')]
            if user.get('ou_managed', []):
                return [(Allow, Authenticated, 'edit')]

        return [(Deny, Everyone, [])]
