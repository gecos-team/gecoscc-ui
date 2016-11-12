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

from gecoscc.models import Setting
import json


def get_setting(key, settings, db):
    value = None
    if db is not None:
        setting = db.settings.find_one({"key": key})
        if setting is not None:
            obj = Setting().serialize(setting)
            value = obj['value']

    if value is None:
        value = settings.get(key)
        # "software_profiles" has a different format in gecoscc.ini
        if key == "software_profiles":
            value = transform_software_profiles(value)

    return value


def transform_software_profiles(software_profiles):
    profiles = json.loads(software_profiles)
    value = u'['
    for name in profiles:
        new_profile = u"{ \"name\":\"%s\", \"packages\":%s }" % (name, json.dumps(profiles[name]))
        if value == u'[':
            value = value + new_profile
        else:
            value = value + u',' + new_profile
    value = value + u']'

    return value
