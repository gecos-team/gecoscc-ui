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


from gecoscc.views.reports import treatment_string_to_csv
from gecoscc.views.reports import treatment_string_to_pdf
from gecoscc.utils import get_filter_nodes_belonging_ou

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPBadRequest

from bson import ObjectId

from gecoscc.i18n import gettext as _

import datetime
import logging
logger = logging.getLogger(__name__)


@view_config(route_name='report_file', renderer='csv',
             permission='is_superuser',
             request_param=("type=audit", "format=csv"))
def report_audit_csv(context, request):
    filename = 'report_audit.csv'
    request.response.content_disposition = 'attachment;filename=' + filename
    return report_audit(context, request, 'csv')

@view_config(route_name='report_file', renderer='pdf',
             permission='is_superuser',
             request_param=("type=audit", "format=pdf"))
def report_audit_pdf(context, request):
    filename = 'report_audit.pdf'
    request.response.content_disposition = 'attachment;filename=' + filename
    return report_audit(context, request, 'pdf')

@view_config(route_name='report_file', renderer='templates/report.jinja2',
             permission='is_superuser',
             request_param=("type=audit", "format=html"))
def report_audit_html(context, request):
    return report_audit(context, request, 'html')


def report_audit(context, request, file_ext):
    '''
    Generate audit log for user information tracking
    
    Args:

    Returns:
        headers (list) : The headers of the table to export
        rows (list)    : Rows with the report data
        widths (list)  : The witdhs of the columns of the table to export
        page           : Translation of the word "page" to the current language
        of             : Translation of the word "of" to the current language
        report_type    : Type of report (html, csv or pdf)
    '''    

    rows = []

    # Getting audit logs
    items = request.db.auditlog.find()

    for item in items:
        row = []
        # Converts timestamp to date
        item['date']  =datetime.datetime.fromtimestamp(item['timestamp']).strftime('%d/%m/%Y %H:%M:%S')

        if file_ext == 'pdf':
            row.append(treatment_string_to_pdf(item, 'action', 10))
            row.append(treatment_string_to_pdf(item, 'username', 15))
            row.append(treatment_string_to_pdf(item, 'ipaddr', 20))
            row.append(item['user-agent'])#treatment_string_to_pdf(item, 'user-agent',100))
            row.append(treatment_string_to_pdf(item, 'date', 80))
        else:
            row.append(treatment_string_to_csv(item, 'action'))
            row.append(treatment_string_to_csv(item, 'username'))
            row.append(treatment_string_to_csv(item, 'ipaddr'))
            row.append(treatment_string_to_csv(item, 'user-agent'))
            row.append(treatment_string_to_csv(item, 'date'))

        rows.append(row)
                
    
    header = (_(u'Action').encode('utf-8'),
              _(u'Username').encode('utf-8'),
              _(u'IP Address').encode('utf-8'),
              _(u'User Agent').encode('utf-8'),
              _(u'Date').encode('utf-8'))
    
    # Column widths in percentage
    widths = (10, 15, 20, 40, 15)
    title =  _(u'Audit report')

    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    return {'headers': header,
            'rows': rows,
            'widths': widths,
            'report_title': title,
            'page': _(u'Page').encode('utf-8'),
            'of': _(u'of').encode('utf-8'),
            'report_type': file_ext,
            'now': now}
