#
# Copyright 2015, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Abraham Macias <amp_21004@yahoo.es>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config

from gecoscc.i18n import gettext as _
from gecoscc.models import Setting, SoftwareProfile
from gecoscc.command_util import get_setting
from gecoscc import messages

from pyramid.threadlocal import get_current_registry
from pyramid.response import Response

import colander
import pymongo

import logging
import json
from bson.objectid import ObjectId
logger = logging.getLogger(__name__)

# Create a setting from the default values
def create_setting(key):
    default_settings = get_current_registry().settings

    setting = Setting()
    setting.key = key

    if key == "update_error_interval":
        appstruct = {'key': key, 'type': 'number', 'value': default_settings.get('update_error_interval')}
    elif key == "repositories":
        appstruct = {'key': key, 'type': 'URLs', 'value': default_settings.get('repositories')}
    elif key == "printers.urls":
        appstruct = {'key': key, 'type': 'URLs', 'value': default_settings.get('printers.urls')}
    elif key == "software_profiles":
        value = get_setting('software_profiles', default_settings, None)
        appstruct = {'key': key, 'type': 'Profiles', 'value': value}
    else:
        appstruct = {'key': key, 'type': 'string', 'value': default_settings.get(key)}

    return Setting().serialize(appstruct)

@view_config(route_name='settings', renderer='templates/settings.jinja2',
             permission='is_superuser')
def settings(context, request):
    settings = request.db.settings.find().sort([("type", pymongo.DESCENDING), ("key", pymongo.ASCENDING)])
    result = []
    if settings.count() == 0:
        # If there aren't settings in the database then load the default values
        
        # firstboot_api.comments
        result.append(create_setting("firstboot_api.comments"))
        
        # firstboot_api.organization_name
        result.append(create_setting("firstboot_api.organization_name"))
        
        # firstboot_api.version
        result.append(create_setting("firstboot_api.version"))

        # update_error_interval
        result.append(create_setting("update_error_interval"))
        
        # repositories
        result.append(create_setting("repositories"))
        
        # printers.urls
        result.append(create_setting("printers.urls"))
        
        # software_profiles
        result.append(create_setting("software_profiles"))
        
        
    else:
        for setting in settings:
            if setting['key'] == "software_profiles":
                # Get software profiles from database
                sp_setting = Setting().deserialize(setting)
                software_profiles = request.db.software_profiles.find()
                
                value = '['
                for sp in software_profiles:
                    del sp['_id']                
                    if value == '[':
                        value = value + json.dumps(sp)
                    else:
                        value = value + ', ' + json.dumps(sp)
                    
                value = value + ']'
                
                Setting().set_value(sp_setting, 'value', value)
                result.append(sp_setting)
            else:
                result.append(Setting().deserialize(setting))
        
    #logger.debug('settings= %s'%(str(result)))
    return { "settings": result }


@view_config(route_name='settings_save', permission='is_superuser')
def settings_save(context, request):
    data = request.POST.get('data')
    settings = request.db.settings.find()
    response = Response()
    if data is not None:
        data = json.loads(data)
        for key in data:
            k = key.replace("___", ".")
            setting_data = request.db.settings.find_one({"key": k })
            if setting_data is None:
                setting = create_setting(k)
            else:
                setting = Setting().deserialize(setting_data)
            
            if isinstance(data[key], str) or isinstance(data[key], unicode):
                Setting().set_value(setting, 'value', data[key])
            else:
                Setting().set_value(setting, 'value', json.dumps(data[key]))
            
            # Save in mongoDB
            obj = Setting().serialize(setting)
            if obj['_id'] == colander.null:
                del obj['_id']
            else:
                obj['_id'] = ObjectId(obj['_id'])
            #logger.debug('save= %s'%(obj))
            request.db.settings.save(obj)
            
            # If saving "software_profiles", save them also in "software_profiles" collection
            if key == "software_profiles":
                collection = request.db.software_profiles
                # Update the software profiles
                for new_profile in data[key]:
                    name = new_profile['name']
                    db_profile = collection.find_one({'name': name})
                    
                    if not db_profile:
                        collection.insert(new_profile)
                        logger.debug("Created profile: %s" % name)

                    elif new_profile['packages'] != db_profile['packages']:
                        collection.update({'name': name}, new_profile)
                        logger.debug("Updated profile: %s" % name)

                # Check if the user is trying to delete a software profile
                sp_policy = request.db.policies.find_one({"slug" : "package_profile_res"})
                if not sp_policy:
                    messages.created_msg(request, _('Software Profiles policy not found'), 'warning')
                    response.write('SUCCESS')
                    return response
                    
                db_profiles = collection.find()
                for profile in db_profiles:
                    profile_found = False
                    for new_profile in data[key]:
                        if new_profile['name'] == profile['name']:
                            profile_found = True
                            
                    if not profile_found:
                        # Check if we can delete the software profile
                        # (the software profile is not in use)
                        logger.debug("Try to delete: %s - %s"%(str(profile['_id']), profile['name']))
                        obj_related_list = "policies.%s.object_related_list"%(str(sp_policy['_id']))
                        profile_id = str(profile['_id'])
                        nnodes = request.db.nodes.find({obj_related_list : profile_id}).count()
                        logger.debug("Found %s nodes"%(nnodes))
                        
                        if nnodes == 0:
                            # It it's not used we can delete it
                            collection.remove({"_id": profile['_id']})
                        else:
                            # It's used, so we can't delete it
                            messages.created_msg(request, _('Software Profile in use: %s')%(profile['name']), 'warning')
                            response.write('SUCCESS')
                            return response
                        
                        
                        
    messages.created_msg(request, _('Settings modified successfully'), 'success')
    response.write('SUCCESS')
    return response

