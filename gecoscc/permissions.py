from pyramid.security import authenticated_userid
from pyramid.httpexceptions import HTTPForbidden, HTTPUnauthorized


def is_logged(request):
    return authenticated_userid(request) is not None


def api_login_required(request):
    if not is_logged(request):
        raise HTTPForbidden('Login required')
