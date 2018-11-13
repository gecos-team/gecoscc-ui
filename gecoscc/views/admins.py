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

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPFound, HTTPMethodNotAllowed
from pyramid.security import forget
from pyramid.threadlocal import get_current_registry
from pyramid.response import FileResponse

from deform import ValidationFailure

from gecoscc import messages
from gecoscc.socks import is_websockets_enabled
from gecoscc.forms import AdminUserAddForm, AdminUserEditForm, AdminUserVariablesForm, AdminUserOUManageForm, MaintenanceForm, UpdateForm
from gecoscc.i18n import gettext as _
from gecoscc.models import AdminUser, AdminUserVariables, AdminUserOUManage, Maintenance, UpdateModel
from gecoscc.pagination import create_pagination_mongo_collection
from gecoscc.utils import delete_chef_admin_user, get_chef_api, toChefUsername, getNextUpdateSeq
from gecoscc.tasks import script_runner

import os
import time
import pickle
import json
import logging
logger = logging.getLogger(__name__)

from chef.exceptions import ChefServerError, ChefServerNotFoundError
from bson import ObjectId

@view_config(route_name='admins', renderer='templates/admins/list.jinja2',
             permission='is_superuser')
def admins(context, request):
    filters = None
    q = request.GET.get('q', None)
    if q:
        filters = {'username': {'$regex': '.*%s.*' % q,
                                '$options': '-i'}}
    admin_users = request.userdb.list_users(filters).sort('username')
    page = create_pagination_mongo_collection(request, admin_users)
    return {'admin_users': admin_users,
            'page': page}

@view_config(route_name='updates', renderer='templates/admins/updates.jinja2',
             permission='is_superuser')
def updates(context, request):
    filters = None
    q = request.GET.get('q', None)
    if q:
        filters = {'name': {'$regex': '.*%s.*' % q,
                            '$options': '-i'}}

    updates = request.db.updates.find(filters).sort('_id',-1)
    
    # "format" filter in jinja2 only admits "%s", not "{0}"
    settings = get_current_registry().settings
    controlfile = settings['updates.control'].replace('{0}','%s')

    latest =  "%04d" % (int(getNextUpdateSeq(request.db))-1)
    page = create_pagination_mongo_collection(request, updates)
    
    return {'updates': updates,
            'latest': latest,
            'controlfile': controlfile,
            'page': page} 


@view_config(route_name='updates_log', permission='is_superuser')
def updates_log(_context, request):
    sequence = request.matchdict['sequence']
    rollback = request.matchdict['rollback']
    settings = get_current_registry().settings
    logfile = settings['updates.rollback'].format(sequence) if rollback else settings['updates.log'].format(sequence)
    response = FileResponse(
        logfile,
        request=request,
        content_type='text/plain'
    )
    headers = response.headers
    headers['Content-Type'] = 'application/download'
    #headers['Accept-Ranges'] = 'bite'
    headers['Content-Disposition'] = 'attachment;filename=' + os.path.basename(logfile)
    headers['Content-Disposition'] = "attachment; filename=\"" + os.path.basename(logfile) + "\"; filename*=UTF-8''"+ unicode(sequence + "_" + os.path.basename(logfile)).encode('utf-8')

    return response


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
        instance['ou_managed_count'] = len(instance.get('ou_managed', [])) or 1
        instance['ou_availables_count'] = len(instance.get('ou_availables', [])) or 1
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
    user = request.db.adminusers.find_one({'username':username})

    # Ous managed by admin (user)
    if not user.get('is_superuser'):
        admin_ous = map(ObjectId, user['ou_managed'])
        ou_managed = [(ou['_id'], ou['name']) for ou in request.db.nodes.find({'_id':{'$in': admin_ous}})]
    else: # Superuser
        ou_managed = [(ou['_id'], ou['name']) for ou in request.db.nodes.find({'type':'ou'})]

    ou_managed = [('', 'Select an Organisational Unit')] + ou_managed

    schema = AdminUserVariables().bind(ou_choices=ou_managed)
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
        raise HTTPMethodNotAllowed("Only delete method is accepted")
    username = request.GET.get('username')
    if request.session['auth.userid'] == username:
        forget(request)
    settings = get_current_registry().settings
    api = get_chef_api(settings, request.user)
    success_remove_chef = delete_chef_admin_user(api, username)
    if not success_remove_chef:
        messages.created_msg(request, _('User deleted unsuccessfully from chef'), 'danger')
    request.userdb.delete_users({'username': username})
    messages.created_msg(request, _('User deleted successfully'), 'success')
    return {'ok': 'ok'}


@view_config(route_name='updates_add', renderer='templates/admins/updates_add.jinja2',
             permission='is_superuser')
def updates_add(context, request):
    schema = UpdateModel()
    form = UpdateForm(schema=schema,
                      request=request)

    instance = controls = {}
    if '_submit' in request.POST:
        controls = request.POST.items()
        logger.info('admin_updates - controls = %s' % controls)
        try:
            params = form.validate(controls)
            logger.info('admin_updates - params = %s' % params)
            form.save(params)
            return HTTPFound(location='')
        except ValidationFailure, e:
            form = e

    if instance and not controls:
        form_render = form.render(instance)
    else:
        form_render = form.render()

    return {
        'update_form': form_render,
    }


@view_config(route_name='updates_tail', permission='is_superuser', renderer='templates/admins/tail.jinja2')
def updates_tail(_context, request):
    logger.info("Tailing log file ...")
    sequence = request.matchdict.get('sequence') 
    rollback = request.matchdict.get('rollback', '')
    logger.debug('admins.py ::: updates_tail - sequence = %s' % sequence)
    logger.debug('admins.py ::: updates_tail - rollback = %s' % rollback)

    if rollback == 'rollback' and request.db.updates.find_one({'_id': sequence}).get('rollback', 0) == 0:
        # Update mongo document
        request.db.updates.update({'_id':sequence},{'$set':{'rollback':1, 'timestamp_rollback': int(time.time()), 'rolluser': request.user['username']}})

        # Celery task
        script_runner.delay(request.user, sequence, rollback=True)

    return { 
        'websockets_enabled': json.dumps(is_websockets_enabled()),
        'request': request,
        'sequence': sequence,
        'rollback': rollback
    }


@view_config(route_name='admin_maintenance', permission='is_superuser', renderer="templates/admins/maintenance.jinja2")
def admin_maintenance(_context, request):

    schemaMaintenance = Maintenance()
    form = MaintenanceForm(schema=schemaMaintenance,
                           request=request)

    data = {}
    settings = get_current_registry().settings
    instance = request.db.settings.find_one({'key':'maintenance_message'})
    if '_submit' in request.POST:
        data = request.POST.items()
        try:
            postdata = form.validate(data)
            logger.debug("admins_log ::: admin_maintenance  = %s" % (postdata))
            form.save(postdata)
            return HTTPFound(location='')
        except ValidationFailure, e:
            form = e

    if instance and not data:
        instance['maintenance_message'] = instance.get('value')
        form_render = form.render(instance)
    else:
        form_render = form.render()

    # Query String: maintenance mode ON/OFF
    mode = request.GET.get('mode', None) 
    logger.info("admin_maintenance ::: mode = %s" % mode)
    obj = request.db.settings.find_one({'key':'maintenance_mode'})
    if obj is None:
        obj = {'key':'maintenance_mode', 'value': mode == 'true', 'type':'string'}
        request.db.settings.insert(obj)

    else:
        if mode is not None:
            request.db.settings.update({'key':'maintenance_mode'},{'$set':{ 'value': mode == 'true' }})
            logger.info("admin_maintenance ::: obj = %s" % (obj))
            if mode == 'false':
                request.db.settings.remove({'key':'maintenance_message'})

    # Active users
    sessions = [pickle.loads(session['value']) for session in request.db.backer_cache.find({},{'_id':0, 'value':1})]
    logger.info("admin_maintenance ::: sessions = %s" % sessions)
    last_action = int(time.time()) - int(settings.get('idle_time',15*60))
    logger.info("admin_maintenance ::: last_action = %s" % last_action)
    active_users = [ session['auth.userid'] for session in sessions if session.get('auth.userid',None) and int(session['_accessed_time']) > last_action ]
    logger.info("admin_maintenance ::: active_users = %s" % active_users)

    filters = {'username':{'$in': active_users }}
    admin_users = request.userdb.list_users(filters).sort('username')
    page = create_pagination_mongo_collection(request, admin_users)

    return {
       'admin_users': admin_users,
       'page': page,
       'maintenance': obj['value'],
       'form_maintenance': form_render
    }



@view_config(route_name='statistics', permission='is_superuser', renderer="templates/admins/statistics.jinja2")
def statistics(context, request):

    object_counters=request.db.nodes.aggregate([ {"$group" : {"_id":"$type", "count":{"$sum":1}}}  ])

    policy_counters=[]

    for pol in request.db.policies.find().sort("name"):
        c=request.db.nodes.find({"policies."+str(pol['_id']): { '$exists': True} } ).count()
        policy_counters.append([pol['name'],c])
         
    return {
       'policy_counters': policy_counters,
       'object_counters': object_counters,
    }


def _check_if_user_belongs_to_admin_group(request, organization, username):
    chefusername = toChefUsername(username)
    settings = get_current_registry().settings
    api = get_chef_api(settings, request.user)
    
    admins_group = api['/organizations/%s/groups/admins'%(organization)]
    if not chefusername in admins_group:
        # Check if exists an association request for this user
        assoc_requests = None
        try:
            assoc_requests = api['/organizations/%s/association_requests'%(organization)]
        except ChefServerNotFoundError:
            pass                    
        
        association_id = None
        for req in assoc_requests:
            if req["username"] == chefusername:
                association_id = req["id"]
        
        if association_id is None:
            # Set an association request for the user in that organization
            try:
                data = {"user": chefusername}
                response = api.api_request('POST', '/organizations/%s/association_requests'%(organization), data=data) 
                association_id = response["uri"].split("/")[-1]
            except ChefServerError:
                # Association already exists?
                pass                    

        if association_id is not None:
            # Accept the association request
            logger.info('Adding %s user to default organization'%(username))
            api.api_request('PUT', '/users/%s/association_requests/%s'%(chefusername, association_id),  data={ "response": 'accept' }) 

        # Add the user to the group
        logger.info('Adding %s user to admins group'%(username))
        admins_group['users'].append(chefusername)
        api.api_request('PUT', '/organizations/%s/groups/admins'%(organization), data={ "groupname": admins_group["groupname"], 
            "actors": {
                "users": admins_group['users'],
                "groups": admins_group["groups"]
            }
            })         
        
        
    
def _admin_edit(request, form_class, username=None):
    admin_user_schema = AdminUser()
    admin_user_form = form_class(schema=admin_user_schema,
                                 collection=request.db['adminusers'],
                                 username=username,
                                 request=request)
    instance = data = {}
    settings = get_current_registry().settings
    if username:
        instance = request.userdb.get_user(username)
    if '_submit' in request.POST:
        data = request.POST.items()
        if username:
            data.append(('username', username))
        try:
            admin_user = admin_user_form.validate(data)
            if username is None:
                username = admin_user['username']
            logger.info('Save %s data in GECOS database'%(username))
            success = admin_user_form.save(admin_user)
            if success:
                # At this moment all GECOS domains are in the "default" Chef organization.
                # So, all the administrator users must belong to the "default" organization's "admins" group
                if int(settings.get('chef.version').split('.')[0]) >= 12 and username is not None:
                    _check_if_user_belongs_to_admin_group(request, 'default', username)
            
                return HTTPFound(location=get_url_redirect(request))
        except ValidationFailure, e:
            admin_user_form = e
    if instance and not data:
        form_render = admin_user_form.render(instance)
    else:
        form_render = admin_user_form.render()
        
    # At this moment all GECOS domains are in the "default" Chef organization.
    # So, all the administrator users must belong to the "default" organization's "admins" group
    if int(settings.get('chef.version').split('.')[0]) >= 12 and username is not None:
        _check_if_user_belongs_to_admin_group(request, 'default', username)
        
    return {'admin_user_form': form_render,
            'username': username,
            'instance': instance,
            'registry': get_current_registry()}


def get_url_redirect(request):
    user = request.user
    if user.get('is_superuser'):
        redirect_view = 'admins'
    else:
        redirect_view = 'home'
    return request.route_url(redirect_view)
