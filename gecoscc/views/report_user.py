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
import datetime
from bson import ObjectId

from gecoscc.views.reports import (treatment_string_to_csv,
    truncate_string_at_char, treatment_string_to_pdf, get_html_node_link,
    check_visibility_of_ou)
from gecoscc.utils import get_filter_nodes_belonging_ou

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPBadRequest

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
    '''
    Generate a report with all the users that belongs to an OU.
    If the administrator is a superadmin the generated report will contain 
    all the users in the database. 
    
    Args:
        ou_id (string) : ID of the OU.

    Returns:
        headers (list) : The headers of the table to export
        rows (list)    : Rows with the report data
        widths (list)  : The witdhs of the columns of the table to export
        page           : Translation of the word "page" to the current language
        of             : Translation of the word "of" to the current language
        report_type    : Type of report (html, csv or pdf)
    '''    

    # Check current user permissions
    ou_id = check_visibility_of_ou(request)
    if ou_id is None:
        raise HTTPBadRequest()

    # Get user data
    query = request.db.nodes.find(
            {'type': 'user','path': get_filter_nodes_belonging_ou(ou_id)})
  
    rows = []

    if file_ext == 'pdf':
        rows = [('&nbsp;'+item['name'],
                 '&nbsp;'+item['first_name']+" "+item['last_name'],
                 '&nbsp;'+item['email'],
                 '&nbsp;'+item['phone'],
                 '&nbsp;'+item['address'],
                 '&nbsp;'+str(item['_id'])) for item in query]
    else:
        rows = [(treatment_string_to_csv(item, 'name') if file_ext == 'csv' else get_html_node_link(item),
                treatment_string_to_csv(item, 'first_name'),
                treatment_string_to_csv(item, 'last_name'),
                treatment_string_to_csv(item, 'email'),
                treatment_string_to_csv(item, 'phone'),
                treatment_string_to_csv(item, 'address'),
                str(item['_id'])) for item in query]

    if file_ext == 'pdf':
        header = (u'Username',
                  u'Name',
                  u'Email',
                  u'Phone',
                  u'Address',
                  u'ID')
    else:
        header = (_(u'Username').encode('utf-8'),
                  _(u'First name').encode('utf-8'),
                  _(u'Last name').encode('utf-8'),
                  _(u'Email').encode('utf-8'),
                  _(u'Phone').encode('utf-8'),
                  _(u'Address').encode('utf-8'),
                  _(u'Id').encode('utf-8'))
    
    # Column widths in percentage
    if file_ext == 'pdf':
        widths = (15, 15, 25, 10, 15, 20)
    else:
        widths = (15, 25, 10, 10, 5, 20, 15)

    title =  _(u'Users report')
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        
    return {'headers': header,
            'rows': rows,
            'widths': widths,
            'report_title': title,
            'page': _(u'Page').encode('utf-8'),
            'of': _(u'of').encode('utf-8'),
            'report_type': file_ext,
            'now': now}
