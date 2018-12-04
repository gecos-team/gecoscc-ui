#
# Copyright 2018, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Abraham Macias <amacias@gruposolutia.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import logging

from gecoscc.views.reports import treatment_string_to_csv

from pyramid.view import view_config

from gecoscc.i18n import gettext as _

logger = logging.getLogger(__name__)


@view_config(route_name='report_file', renderer='csv',
             permission='edit',
             request_param=("type=user", "format=csv"))
def report_user_csv(context, request):
    filename = 'report_user.csv'
    request.response.content_disposition = 'attachment;filename=' + filename
    return report_user(context, request, 'csv')

@view_config(route_name='report_file', renderer='pdf',
             permission='edit',
             request_param=("type=user", "format=pdf"))
def report_user_pdf(context, request):
    filename = 'report_user.pdf'
    request.response.content_disposition = 'attachment;filename=' + filename
    return report_user(context, request, 'pdf')

@view_config(route_name='report_file', renderer='templates/report.jinja2',
             permission='edit',
             request_param=("type=user", "format=html"))
def report_user_html(context, request):
    return report_user(context, request, 'html')


def report_user(context, request, file_ext):
    query = request.db.nodes.find({'type': 'user'})
  
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
    
    # Column widths in percentage
    widths = (20, 10, 10, 10, 20, 10, 20)
    title =  _(u'Users report')
        
        
    return {'headers': header,
            'rows': rows,
            'widths': widths,
            'report_title': title,
            'page': _(u'Page').encode('utf-8'),
            'of': _(u'of').encode('utf-8'),
            'report_type': file_ext}
