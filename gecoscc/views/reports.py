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

import csv

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


from pyramid.httpexceptions import HTTPBadRequest
from pyramid.view import view_config

from gecoscc.i18n import gettext as _


class CSVRenderer(object):

    def __init__(self, info):
        pass

    def __call__(self, value, system):
        """ Returns a plain CSV-encoded string with content-type
        ``text/csv``. The content-type may be overridden by
        setting ``request.response.content_type``."""

        request = system.get('request')
        if request is not None:
            response = request.response
            ct = response.content_type
            if ct == response.default_content_type:
                response.content_type = 'text/csv'

        fout = StringIO()
        writer = csv.writer(fout, delimiter=',', quotechar=',', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(value.get('header', []))
        writer.writerows(value.get('rows', []))
        return fout.getvalue()


@view_config(route_name='reports', renderer='templates/reports.jinja2',
             permission='edit')
def reports(context, request):
    return {}


def treatment_string_to_csv(item, key):
    none = '--'
    return item.get(key, none).encode('utf-8') or none


@view_config(route_name='report_file', renderer='csv',
             permission='edit')
def report_file(context, request):
    report_type = request.matchdict.get('report_type')
    filename = 'report_%s.csv' % report_type
    request.response.content_disposition = 'attachment;filename=' + filename
    if report_type not in ('user', 'computer'):
        raise HTTPBadRequest()
    query = request.db.nodes.find({'type': report_type})
    if report_type == 'user':
        rows = [(item['_id'],
                 treatment_string_to_csv(item, 'name'),
                 treatment_string_to_csv(item, 'first_name'),
                 treatment_string_to_csv(item, 'last_name'),
                 treatment_string_to_csv(item, 'email'),
                 treatment_string_to_csv(item, 'phone'),
                 treatment_string_to_csv(item, 'address')) for item in query]
        header = (_(u'Id').encode('utf-8'),
                  _(u'Username').encode('utf-8'),
                  _(u'First name').encode('utf-8'),
                  _(u'Last name').encode('utf-8'),
                  _(u'Email').encode('utf-8'),
                  _(u'Phone').encode('utf-8'),
                  _(u'Address').encode('utf-8'))
    elif report_type == 'computer':
        rows = [(item['_id'],
                 treatment_string_to_csv(item, 'name'),
                 treatment_string_to_csv(item, 'family'),
                 treatment_string_to_csv(item, 'registry'),
                 treatment_string_to_csv(item, 'serial'),
                 treatment_string_to_csv(item, 'node_chef_id')) for item in query]
        header = (_(u'Id').encode('utf-8'),
                  _(u'Name').encode('utf-8'),
                  _(u'Type').encode('utf-8'),
                  _(u'Registry number').encode('utf-8'),
                  _(u'Serial number').encode('utf-8'),
                  _(u'Node chef id').encode('utf-8'))
    return {'header': header,
            'rows': rows}
