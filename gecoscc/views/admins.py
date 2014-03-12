from pyramid.view import view_config

from deform import ValidationFailure

from gecoscc.forms import AdminUserForm
from gecoscc.models import AdminUser


@view_config(route_name='admins', renderer='templates/admins/list.jinja2',
             permission='edit')
def admins(context, request):
    return {'admin_users': request.userdb.list_users()}


@view_config(route_name='admins_add', renderer='templates/admins/add.jinja2',
             permission='edit')
def admin_add(context, request):
    admin_user_schema = AdminUser()
    admin_user_form = AdminUserForm(admin_user_schema)
    if 'submit' in request.POST:
        data = request.POST.items()
        try:
            admin_user = admin_user_form.validate(data)
            request.db['adminusers'].insert(admin_user)
        except ValidationFailure, e:
            admin_user_form = e
    return {'admin_user_form': admin_user_form}
