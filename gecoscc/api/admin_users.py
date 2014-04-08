from cornice.resource import resource
from pyramid.httpexceptions import HTTPForbidden
from pyramid.security import remember

from gecoscc.api import ResourcePaginatedReadOnly
from gecoscc.models import AdminUser
from gecoscc.permissions import api_login_required
from gecoscc.userdb import UserDoesNotExist


def admin_user_login_required(request):
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


@resource(path='/auth/config/',
          description='Auth config',
          validators=admin_user_login_required)
class AdminUserResource(ResourcePaginatedReadOnly):

    schema_detail = AdminUser
    collection_name = 'adminusers'
    objtype = 'adminusers'

    def get(self):
        return self.parse_item(self.request.user)