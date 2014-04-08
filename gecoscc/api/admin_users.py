from cornice.resource import resource
from pyramid.httpexceptions import HTTPForbidden

from gecoscc.api import ResourcePaginatedReadOnly
from gecoscc.models import AdminUser
from gecoscc.permissions import api_login_required


def admin_user_login_required(request):
    try:
        api_login_required(request)
    except HTTPForbidden, e:
        authorization = request.headers.get('Authorization')
        if not authorization:
            raise e
        user, password = authorization.replace('Basic ', '').decode('base64').split(':')
        is_login = request.userdb.login(user, password)
        if not is_login:
            raise e


@resource(path='/auth/config/',
          description='Auth config',
          validators=admin_user_login_required)
class AdminUserResource(ResourcePaginatedReadOnly):

    schema_detail = AdminUser
    collection_name = 'adminusers'
    objtype = 'adminusers'

    def get(self):
        return self.parse_item(self.request.user)