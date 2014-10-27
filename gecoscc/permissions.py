from bson import ObjectId

from pyramid.httpexceptions import HTTPForbidden
from pyramid.security import (Allow, Authenticated, Everyone, ALL_PERMISSIONS,
                              authenticated_userid, forget, remember)


from gecoscc.userdb import UserDoesNotExist
from gecoscc.utils import is_domain, get_domain, MASTER_DEFAULT, RESOURCES_EMITTERS_TYPES


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
    if path is None:
        path = ''
    ou_managed_ids = request.user.get(ou_type, [])
    for ou_managed_id in ou_managed_ids:
        if ou_managed_id in path:
            return True
            break
    return False


def can_access_to_this_path(request, collection_nodes, oid_or_obj, ou_type='ou_managed'):
    obj = None
    request = request
    ou_managed_ids = request.user.get(ou_type, [])
    if not request.user.get('is_superuser') or ou_managed_ids:
        if isinstance(oid_or_obj, dict):
            obj = oid_or_obj
        else:
            obj = collection_nodes.find_one({'_id': ObjectId(oid_or_obj)})
        path = obj['path']
        if '_id' in obj:
            path = '%s,%s' % (path, obj['_id'])
        if not is_path_right(request, path, ou_type):
            if not is_domain(obj) or not request.method == 'GET':
                raise HTTPForbidden()


def is_gecos_master_or_403(request, collection_nodes, obj):
    domain = get_domain(obj, collection_nodes)
    if domain and domain['master'] != MASTER_DEFAULT:
        raise HTTPForbidden()


def master_policy_no_updated_or_403(request, collection_nodes, obj):
    if obj['type'] in RESOURCES_EMITTERS_TYPES:
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
        for policy_id, value in master_policies.items():
            if mongo_policies.get(policy_id, None) != policies.get(policy_id, None):
                raise HTTPForbidden()


def nodes_path_filter(request):
    params = request.GET
    maxdepth = int(params.get('maxdepth', 0))
    path = request.GET.get('path', None)
    range_depth = '0,{0}'.format(maxdepth)
    ou_managed_ids = request.user.get('ou_managed', [])
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
        elif not is_path_right(request, path):
            raise HTTPForbidden()
    elif request.user.get('is_superuser') and path is None:
        return {}
    return {
        'path': {
            '$regex': r'^{0}(,[^,]*){{{1}}}$'.format(path, range_depth),
        }
    }


class RootFactory(object):
    __acl__ = [
        (Allow, Everyone, ALL_PERMISSIONS),
    ]

    def __init__(self, request):
        self.request = request

    def get_groups(self, userid, request):
        return []


class LoggedFactory(object):
    __acl__ = [
        (Allow, Authenticated, ALL_PERMISSIONS),
    ]

    def __init__(self, request):
        self.request = request
        try:
            self.request.user
        except UserDoesNotExist:
            forget(request)

    def get_groups(self, userid, request):
        return []


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
            if is_superuser or user.get('username') == username:
                return [(Allow, Authenticated, ALL_PERMISSIONS)]
        return [(Allow, Authenticated, [])]