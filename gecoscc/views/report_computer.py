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
             request_param=("type=computer", "format=csv"))
def report_computer_csv(context, request):
    filename = 'report_computer.csv'
    request.response.content_disposition = 'attachment;filename=' + filename    
    return report_computer(context, request, 'csv')

@view_config(route_name='report_file', renderer='pdf',
             permission='edit',
             request_param=("type=computer", "format=pdf"))
def report_computer_pdf(context, request):
    filename = 'report_computer.pdf'
    request.response.content_disposition = 'attachment;filename=' + filename    
    return report_computer(context, request, 'pdf')

@view_config(route_name='report_file', renderer='templates/report.jinja2',
             permission='edit',
             request_param=("type=computer", "format=html"))
def report_computer_html(context, request):
    return report_computer(context, request, 'html')


def report_computer(context, request, file_ext):
        
    query = request.db.nodes.find({'type': 'computer'})
  
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
    
    # Column widths in percentage
    widths = (20, 10, 10, 10, 15, 15, 15)
    title =  _(u'Computers report')
        
        
    return {'headers': header,
            'rows': rows,
            'widths': widths,
            'report_title': title,
            'page': _(u'Page').encode('utf-8'),
            'of': _(u'of').encode('utf-8'),
            'report_type': file_ext}
