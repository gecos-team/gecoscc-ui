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
from babel.dates import format_datetime, LOCALTZ


def admin_serialize(admin):
    serialized = AdminUser().serialize(admin)
    serialized.update({
        'ou_readonly': admin.get('ou_readonly', []),
        'ou_managed': admin.get('ou_managed', []),
        'ou_remote': admin.get('ou_remote', [])
    })
    json_data = ''
    try:
        json_data = json.dumps(serialized)
    except TypeError as e:
        json_data = 'Error serializing user: %s' % (str(e))
    
    return json_data

def datetime(value, date_format='medium'):
    '''
    Custom filter for formatting date in jinja2 template
    '''
    if date_format == 'full':
        date_format="EEEE d/MMM/y HH:mm"
    elif date_format == 'medium':
        date_format="dd/MM/y HH:mm"
    return format_datetime(value, date_format, tzinfo=LOCALTZ)


def timediff(value):
    '''
    Custom filter for formatting time differences in jinja2 template
    '''
    
    if not 'timestamp' in value or not 'timestamp_end' in value:
        return '';
    
    start_time = value['timestamp']
    end_time = value['timestamp_end']
    difference = (end_time - start_time)
    
    formatted = ''
    seconds = (difference % 60)
    difference = ((difference - seconds) / 60)
    
    minutes = (difference % 60)
    difference = ((difference - minutes) / 60)    

    hours = (difference % 24)
    days = ((difference - minutes) / 24)    
    
    if days > 0:
        formatted += '%sd '%(days)

    if hours > 0:
        formatted += '%sh '%(hours)

    if minutes > 0:
        formatted += '%sm '%(minutes)

    if seconds > 0:
        formatted += '%ss '%(seconds)
    
    return '(' + formatted.strip() +')'

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
