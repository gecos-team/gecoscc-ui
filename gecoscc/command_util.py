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


def get_setting(key, settings, db):
    value = None
    if db is not None:
        setting = db.settings.find_one({"key": key})
        if setting is not None:
            obj = Setting().serialize(setting)
            value = obj['value']

    if value is None:
        value = settings.get(key)

    return value


