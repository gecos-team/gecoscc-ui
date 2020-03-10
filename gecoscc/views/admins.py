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
from pyramid.httpexceptions import HTTPFound, HTTPMethodNotAllowed, HTTPNotFound
from pyramid.security import forget
from pyramid.threadlocal import get_current_registry
from pyramid.response import FileResponse

from deform import ValidationFailure

from gecoscc import messages
from gecoscc.socks import is_websockets_enabled
from gecoscc.forms import (AdminUserAddForm, AdminUserEditForm, AdminUserVariablesForm,
    MaintenanceForm, UpdateForm, PermissionsForm)
from gecoscc.i18n import gettext as _
from gecoscc.models import (AdminUser, AdminUserVariables, Maintenance, UpdateModel, AdminUserOUPerms,
    AdminUserOUPerm, Permissions)
from gecoscc.pagination import create_pagination_mongo_collection
from gecoscc.utils import delete_chef_admin_user, get_chef_api, toChefUsername, getNextUpdateSeq, get_filter_nodes_belonging_ou
from gecoscc.tasks import script_runner
from gecoscc.views.reports import get_complete_path

import os
import pymongo
import time
import pickle
import json
import collections
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
    filters = {}
    q = request.GET.get('q', None)
    if q:
        filters = {'name': {'$regex': '.*%s.*' % q,
                            '$options': '-i'}}

    # Order
    order = request.GET.get('order', None)
    if order:
        if order == "desc":
            ordering = pymongo.DESCENDING
        elif order == "asc":
            ordering = pymongo.ASCENDING
    logger.debug("admins.py ::: updates - order = {}".format(order))

    # Orderby
    sorting = ('timestamp', -1) # default
    s = request.GET.get('orderby', None)
    if s:
        if s == '_id':
            sorting = ('_id', ordering)
        elif s == 'name':
            sorting = ('name', ordering)
        elif s == 'log':
            sorting = ('timestamp', ordering)

    logger.debug("admins.py ::: updates - sorting = {}".format(sorting))
    updates = request.db.updates.find(filters).sort([sorting])
    
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
    logfile = settings['updates.rollback'].format(sequence)
    if not rollback:
        logfile = settings['updates.log'].format(sequence)
    
    if not os.path.isfile(logfile):
        raise HTTPNotFound()
    
    response = FileResponse(
        logfile,
        request=request,
        content_type='text/plain'
    )
    headers = response.headers
    headers['Content-Type'] = 'application/download'
    headers['Content-Disposition'] = "attachment; filename=\"" + \
        os.path.basename(logfile) + "\"; filename*=UTF-8''"+ \
        unicode(sequence + "_" + os.path.basename(logfile)).encode('utf-8')

    return response


@view_config(route_name='updates_download', permission='is_superuser')
def updates_download(_context, request):
    settings = get_current_registry().settings
    _id = request.matchdict['id']
    
    update = request.db.updates.find_one({'_id': _id})
    if update is None:
        raise HTTPNotFound()
    
    update_file = os.path.join(settings['updates.dir'],
                               update['_id'],
                               update['name'])
    if not os.path.isfile(update_file):
        raise HTTPNotFound()
        
    response = FileResponse(
        update_file,
        request=request,
        content_type='application/zip'
    )
    headers = response.headers
    headers['Content-Type'] = 'application/download'
    headers['Content-Disposition'] = 'attachment;filename=' + \
        str(update['name'])

    return response


@view_config(route_name='admins_ou_manage', renderer='templates/admins/ou_manage.jinja2',
             permission='is_superuser')
def admins_ou_manage(context, request):
    ou_choices = [(ou['_id'], ou['name']) for ou in request.db.nodes.find({'type': 'ou', 'path': 'root'})]
    ou_choices = [('', 'Select an Organisational Unit')] + ou_choices
    username = request.matchdict['username']
    schema = Permissions().bind(ou_choices=ou_choices)
    form = PermissionsForm(schema=schema,
                           collection=request.db['adminusers'],
                           username=username,
                           request=request)
    controls = {}
    instance = request.userdb.get_user(username)
    if '_submit' in request.POST:
        controls = request.POST.items()
        # Removing blanks OUs (not filling up by user)
        data = [tup for tup in controls if not (tup[0] == 'ou_selected' and tup[1] == '')]
        logger.debug("admins_ou_manage ::: data = {}".format(data))

        try:
            deserialized = form.validate(data)
            form.save(deserialized['perms'])
            return HTTPFound(location=get_url_redirect(request))
        except ValidationFailure as e:
            logger.error("admins_ou_manage ::: ValidationFailure = {}".format(e))
            form = e

    if instance and not controls:
        # instance = {'perms': [
        #     {'permission': [u'READONLY', u'LINK'], 'ou_selected': [u'562f7adee488e3664c6264e5']},
        #     {'permission': [u'REMOTE'], 'ou_selected': [u'5821789be488e34fcd2cf61c']},
        #     {'permission': [u'MANAGE'], 'ou_selected': [u'5526358508d70a63c6024794']}
        # ]}

        # Mapping model to appstruct
        instance['perms'] = []
        ou_managed = instance.get('ou_managed', [])
        ou_availables = instance.get('ou_availables', [])
        ou_remote = instance.get('ou_remote', [])
        ou_readonly = instance.get('ou_readonly', [])

        ous = set(ou_managed + ou_availables + ou_remote + ou_readonly)

        for ou in ous:

            perm = {'permission': [], 'ou_selected': [ou]}

            if ou in ou_managed:
                perm['permission'].append('MANAGE')
            if ou in ou_availables:
                perm['permission'].append('LINK')
            if ou in ou_remote:
                perm['permission'].append('REMOTE')
            if ou in ou_readonly:
                perm['permission'].append('READONLY')

            instance['perms'].append(perm)

        form_render = form.render(instance)
    else:
        form_render = form.render()

    return {
        'ou_manage_form': form_render,
        'username': username
    }


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
        if 'ou_managed' in user:
            admin_ous = map(ObjectId, user['ou_managed'])
            ou_managed = [(ou['_id'], ou['name']) for ou in request.db.nodes.find({'_id': {'$in': admin_ous}})]
        else: # Recently new admin created
            ou_managed = []
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



@view_config(route_name='statistics', permission='edit', renderer="templates/admins/statistics.jinja2")
def statistics(context, request):

    object_counters = []
    policy_counters = []
    ous = {}
    ous_visibles = []
    settings = get_current_registry().settings
    policyname = "name_{}".format(settings['pyramid.default_locale_name'])

    is_superuser = request.user.get('is_superuser', False)
    ou_id = request.GET.get('ou_id', None)
    logger.debug("admins.py ::: statistics - ou_id = {}".format(ou_id))

    if is_superuser:
        ous_visibles = request.db.nodes.find(
            {"type": "ou"},
            {"_id": 1, "name": 1, "path": 1}
        )
    else:
        # Get managed ous for admin
        oids = request.user.get('ou_managed', []) + request.user.get('ou_readonly', [])
        ous_visibles = request.db.nodes.find(
            {"_id": { "$in": map(ObjectId, oids) }},
            {"_id": 1, "name": 1, "path": 1}
        )
    for ou in ous_visibles:
        path = ou['path'] + ',' + str(ou['_id'])
        ous.update({str(ou['_id']): get_complete_path(request.db, path)})

    sorted_ous = collections.OrderedDict(sorted(ous.items(), key=lambda kv: len(kv[1])))
    logger.debug("admins.py ::: statistics - sorted_ous = {}".format(sorted_ous))

    # Defaults
    if not ou_id:
        ou_id = str(sorted_ous.items()[0][0])

    logger.debug("admins.py ::: statistics - ou_id = {}".format(ou_id))

    # Objects
    object_counters = request.db.nodes.aggregate([
        {"$match" : { "path": get_filter_nodes_belonging_ou(ou_id)}},
        {"$group" : { "_id" : "$type", "count": {"$sum":1}}}
    ], cursor={})

    logger.debug("admins.py ::: statistics - object_counters = {}".format(object_counters))

    # Policies
    for pol in request.db.policies.find().sort("name"):
        c = request.db.nodes.find({
            "$or": [{"path": get_filter_nodes_belonging_ou(ou_id)}, {"_id":ObjectId(ou_id)}],
            "policies." + str(pol['_id']): {'$exists': True}
        }).count()
        try:
            policy_counters.append([pol[policyname],c])
        except KeyError:
            policy_counters.append([pol['name'],c])

    logger.debug("admins.py ::: statistics - policy_counters = {}".format(policy_counters))

    return {
       'policy_counters': policy_counters,
       'object_counters': object_counters,
       'ou_managed': sorted_ous,
       'ou_selected': ou_id,
       'is_superuser': is_superuser
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
