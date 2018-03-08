#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Author:
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import json


from gecoscc.models import AdminUser
from babel.dates import format_datetime


def admin_serialize(admin):
    return json.dumps(AdminUser().serialize(admin));

def datetime(value, format='medium'):
    if format == 'full':
        format="EEEE d/MMM/y HH:mm"
    elif format == 'medium':
        format="dd/MM/y HH:mm"
    return format_datetime(value, format)