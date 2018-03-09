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
import re
import six

from gecoscc.models import AdminUser
from babel.dates import format_datetime


def admin_serialize(admin):
    return json.dumps(AdminUser().serialize(admin));

def datetime(value, format='medium'):
    '''
    Custom filter for formatting date in jinja2 template
    '''
    if format == 'full':
        format="EEEE d/MMM/y HH:mm"
    elif format == 'medium':
        format="dd/MM/y HH:mm"
    return format_datetime(value, format)

def _get_regex_flags(ignorecase=False):
    return re.I if ignorecase else 0

def regex_match(value, pattern='', ignorecase=False):
    '''
    Custom filter for matching regular expression in jinja2 template
    '''
    if not isinstance(value, six.string_types):
        value = str(value)
    flags = _get_regex_flags(ignorecase)
    return bool(re.match(pattern, value, flags))