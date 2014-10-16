from pyramid.httpexceptions import HTTPForbidden
from pyramid.security import (Allow, Authenticated, Everyone, ALL_PERMISSIONS,
                              authenticated_userid, forget, remember)


from gecoscc.userdb import UserDoesNotExist


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


def is_path_right(request, path):
    ou_managed_ids = request.user.get('ou_managed', [])
    for ou_managed_id in ou_managed_ids:
        if ou_managed_id in path:
            return True
            break
    return False


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