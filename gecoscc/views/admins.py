from pyramid.view import view_config

from deform import ValidationFailure

from gecoscc.forms import AdminUserAddForm, AdminUserEditForm
from gecoscc.models import AdminUser


@view_config(route_name='admins', renderer='templates/admins/list.jinja2',
             permission='edit')
def admins(context, request):
    return {'admin_users': request.userdb.list_users()}


@view_config(route_name='admins_add', renderer='templates/admins/add.jinja2',
             permission='edit')
def admin_add(context, request):
    return _admin_edit(request, AdminUserAddForm)


@view_config(route_name='admins_edit', renderer='templates/admins/add.jinja2',
             permission='edit')
def admin_edit(context, request):
    return _admin_edit(request, AdminUserEditForm, username=request.matchdict['username'])


def _admin_edit(request, form_class, username=None):
    admin_user_schema = AdminUser()
    admin_user_form = form_class(schema=admin_user_schema,
                                 collection=request.db['adminusers'])
    instance = data = {}
    if username:
        instance = request.userdb.list_users({'username': username})[0]
    if 'submit' in request.POST:
        data = request.POST.items()
        try:
            admin_user = admin_user_form.validate(data)
            admin_user_form.save(admin_user)
        except ValidationFailure, e:
            admin_user_form = e
    if instance and not data:
        form_render = admin_user_form.render(instance)
    else:
        form_render = admin_user_form.render()
    return {'admin_user_form': form_render}
