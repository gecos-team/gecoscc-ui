from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound, HTTPMethodNotAllowed
from pyramid.security import forget

from deform import ValidationFailure

from gecoscc import messages
from gecoscc.forms import AdminUserAddForm, AdminUserEditForm, AdminUserVariablesForm, AdminUserOUManageForm
from gecoscc.i18n import TranslationString as _
from gecoscc.models import AdminUser, AdminUserVariables, AdminUserOUManage
from gecoscc.pagination import create_pagination_mongo_collection


@view_config(route_name='admins', renderer='templates/admins/list.jinja2',
             permission='is_superuser')
def admins(context, request):
    filters = None
    q = request.GET.get('q', None)
    if q:
        filters = {'username': {'$regex': '.*%s.*' % q}}
    admin_users = request.userdb.list_users(filters).sort('username')
    page = create_pagination_mongo_collection(request, admin_users)
    return {'admin_users': admin_users,
            'page': page}


@view_config(route_name='admins_superuser', renderer='templates/admins/variables.jinja2', permission='is_superuser')
def admins_superuser(context, request):
    username = request.matchdict['username']
    if '_superuser' in request.POST:
        is_superuser = True
        message = _('Now the user is a super user')
    elif '_no_superuser' in request.POST:
        is_superuser = False
        message = _('Now the user is not a super user')
    request.userdb.collection.update({'username': username}, {'$set': {'is_superuser': is_superuser}})
    messages.created_msg(request, message, 'success')
    return HTTPFound(location=request.route_url('admins'))


@view_config(route_name='admins_ou_manage', renderer='templates/admins/ou_manage.jinja2',
             permission='is_superuser')
def admins_ou_manage(context, request):
    ou_choices = [(ou['_id'], ou['name']) for ou in request.db.nodes.find({'type': 'ou', 'path': 'root'})]
    ou_choices = [('', 'Select an Organisational Unit')] + ou_choices
    username = request.matchdict['username']
    schema = AdminUserOUManage().bind(ou_choices=ou_choices)
    form = AdminUserOUManageForm(schema=schema,
                                 collection=request.db['adminusers'],
                                 username=username,
                                 request=request)
    data = {}
    instance = request.userdb.get_user(username)
    if '_submit' in request.POST:
        data = request.POST.items()
        ous_variables = {}
        try:
            for field_name in ['ou_managed', 'ou_availables']:
                ous_variables[field_name] = []
                field_name_count = '%s_count' % (field_name)
                for i in range(int(request.POST.get(field_name_count))):
                    if i != 0:
                        field_name_iter = '%s-%s' % (field_name, i)
                    else:
                        field_name_iter = field_name
                    ous = request.POST.getall(field_name_iter)
                    if len(ous) == 0:
                        last_ou = ''
                    else:
                        if len(ous) > 1 and ous[-1] == '':
                            last_ou = ous[-2]
                        else:
                            last_ou = ous[-1]
                    if last_ou:
                        ous_variables[field_name].append(last_ou)
            form.save(ous_variables)
            return HTTPFound(location=get_url_redirect(request))
        except ValidationFailure, e:
            form = e
    if instance and not data:
        form_render = form.render(instance)
    else:
        form_render = form.render()
    return {'ou_manage_form': form_render,
            'username': username}


@view_config(route_name='admins_add', renderer='templates/admins/add.jinja2',
             permission='is_superuser')
def admin_add(context, request):
    return _admin_edit(request, AdminUserAddForm)


@view_config(route_name='admins_edit', renderer='templates/admins/edit.jinja2',
             permission='is_superuser_or_my_profile')
def admin_edit(context, request):
    return _admin_edit(request, AdminUserEditForm,
                       username=request.matchdict['username'])


@view_config(route_name='admins_set_variables', renderer='templates/admins/variables.jinja2',
             permission='is_superuser_or_my_profile')
def admins_set_variables(context, request):
    username = request.matchdict['username']
    schema = AdminUserVariables()
    form = AdminUserVariablesForm(schema=schema,
                                  collection=request.db['adminusers'],
                                  username=username,
                                  request=request)
    data = {}
    instance = request.userdb.get_user(username).get('variables', None)
    if '_submit' in request.POST:
        data = request.POST.items()
        try:
            variables = form.validate(data)
            form.save(variables)
            return HTTPFound(location=get_url_redirect(request))
        except ValidationFailure, e:
            form = e
    if instance and not data:
        form_render = form.render(instance)
    else:
        form_render = form.render()
    return {'variables_form': form_render,
            'username': username}


@view_config(route_name='admin_delete', permission='is_superuser_or_my_profile',  xhr=True, renderer='json')
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
            return HTTPFound(location=get_url_redirect(request))
        except ValidationFailure, e:
            admin_user_form = e
    if instance and not data:
        form_render = admin_user_form.render(instance)
    else:
        form_render = admin_user_form.render()
    return {'admin_user_form': form_render,
            'username': username,
            'instance': instance}


def get_url_redirect(request):
    user = request.user
    if user.get('is_superuser'):
        redirect_view = 'admins'
    else:
        redirect_view = 'home'
    return request.route_url(redirect_view)
