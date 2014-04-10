from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound, HTTPMethodNotAllowed
from pyramid.security import forget

from deform import ValidationFailure

from gecoscc import messages
from gecoscc.forms import AdminUserAddForm, AdminUserEditForm, AdminUserVariablesForm
from gecoscc.i18n import TranslationString as _
from gecoscc.models import AdminUser, AdminUserVariables
from gecoscc.pagination import create_pagination_mongo_collection


@view_config(route_name='admins', renderer='templates/admins/list.jinja2',
             permission='edit')
def admins(context, request):
    filters = None
    q = request.GET.get('q', None)
    if q:
        filters = {'username': {'$regex': '.*%s.*' % q}}
    admin_users = request.userdb.list_users(filters)
    page = create_pagination_mongo_collection(request, admin_users)
    return {'admin_users': admin_users,
            'page': page}


@view_config(route_name='admins_add', renderer='templates/admins/add.jinja2',
             permission='edit')
def admin_add(context, request):
    return _admin_edit(request, AdminUserAddForm)


@view_config(route_name='admins_edit', renderer='templates/admins/edit.jinja2',
             permission='edit')
def admin_edit(context, request):
    return _admin_edit(request, AdminUserEditForm,
                       username=request.matchdict['username'])


@view_config(route_name='admins_set_variables', renderer='templates/admins/variables.jinja2',
             permission='edit')
def admins_set_variables(context, request):
    username = request.matchdict['username']
    schema = AdminUserVariables()
    form = AdminUserVariablesForm(schema=schema,
                                  collection=request.db['adminusers'],
                                  username=username,
                                  request=request)
    instance = data = {}
    if username:
        instance = request.userdb.get_user(username)
    if '_submit' in request.POST:
        data = request.POST.items()
        try:
            admin_user = form.validate(data)
            form.save(admin_user)
            return HTTPFound(location=request.route_url('admins'))
        except ValidationFailure, e:
            form = e
    if instance and not data:
        form_render = form.render(instance)
    else:
        form_render = form.render()
    return {'admin_user_form': form_render,
            'username': username}


@view_config(route_name='admin_delete', permission='edit',  xhr=True, renderer='json')
def admin_delete(context, request):
    if request.method != 'DELETE':
        raise HTTPMethodNotAllowed("Only delete mthod is accepted")
    username = request.GET.get('username')
    if request.session['auth.userid'] == username:
        forget(request)
    request.userdb.delete_users({'username': username})
    messages.created_msg(request, _('User deleted successfully'), 'success')
    return {'ok': 'ok'}


def _admin_edit(request, form_class, username=None):
    admin_user_schema = AdminUser()
    admin_user_form = form_class(schema=admin_user_schema,
                                 collection=request.db['adminusers'],
                                 username=username,
                                 request=request)
    instance = data = {}
    if username:
        instance = request.userdb.get_user(username)
    if '_submit' in request.POST:
        data = request.POST.items()
        try:
            admin_user = admin_user_form.validate(data)
            admin_user_form.save(admin_user)
            return HTTPFound(location=request.route_url('admins'))
        except ValidationFailure, e:
            admin_user_form = e
    if instance and not data:
        form_render = admin_user_form.render(instance)
    else:
        form_render = admin_user_form.render()
    return {'admin_user_form': form_render,
            'username': username}
