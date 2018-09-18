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

from pyramid.view import view_config

from gecoscc.i18n import gettext as _
from gecoscc.models import Setting
from gecoscc import messages

from pyramid.threadlocal import get_current_registry
from pyramid.response import Response

import colander
import pymongo

import logging
import json
from bson.objectid import ObjectId
logger = logging.getLogger(__name__)

# This settings, which are not set in the view, are saved in MongoDB collection
EXCLUDE_SETTINGS = ['maintenance_mode']

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
    elif key ==  "mimetypes":
        appstruct = {'key': key, 'type': 'Mimetypes', 'value': default_settings.get(key)}
    else:
        appstruct = {'key': key, 'type': 'string', 'value': default_settings.get(key)}

    return Setting().serialize(appstruct)

@view_config(route_name='settings', renderer='templates/settings.jinja2',
             permission='is_superuser')
def settings(_context, request):
    settings_data = request.db.settings.find({'key':{'$nin': EXCLUDE_SETTINGS}}).sort([("type", pymongo.DESCENDING), ("key", pymongo.ASCENDING)])
    result = []
    if settings_data.count() == 0:
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
        
        # mimetypes
        result.append(create_setting("mimetypes"))
        
        
    else:
        includesMimeTypes = False
        for setting in settings_data:
            if setting['key'] == "mimetypes":
                includesMimeTypes = True
                result.append(Setting().deserialize(setting))
            else:
                result.append(Setting().deserialize(setting))
    
        if not includesMimeTypes:
            result.append(create_setting("mimetypes"))
    #logger.debug('settings= %s'%(str(result)))
    return { "settings": result }


@view_config(route_name='settings_save', permission='is_superuser')
def settings_save(_context, request):
    data = request.POST.get('data')
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
                                    
    messages.created_msg(request, _('Settings modified successfully'), 'success')
    response.write('SUCCESS')
    return response

