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

from gecoscc.views.reports import (treatment_string_to_csv,
    treatment_string_to_pdf, get_html_node_link, check_visibility_of_ou)
from gecoscc.utils import get_filter_nodes_belonging_ou

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPBadRequest

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
    '''
    Generate a report with all the computers that belongs to an OU.
    If the administrator is a superadmin the generated report will contain 
    all the computers in the database. 

    
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
            {'type': 'computer', 'path': get_filter_nodes_belonging_ou(ou_id)})

    if file_ext == 'pdf':
        rows = [(treatment_string_to_pdf(item, 'name', 20),
                 treatment_string_to_pdf(item, 'family', 10),
                 treatment_string_to_pdf(item, 'registry', 10),
                 treatment_string_to_pdf(item, 'serial', 15),
                 #treatment_string_to_pdf(item, 'node_chef_id', 25),
                 item['_id']) for item in query]
    else:
        rows = [(treatment_string_to_csv(item, 'name') if file_ext == 'csv' \
                    else get_html_node_link(item),
                 treatment_string_to_csv(item, 'family'),
                 treatment_string_to_csv(item, 'registry'),
                 treatment_string_to_csv(item, 'serial'),
                 #treatment_string_to_csv(item, 'node_chef_id'),
                 item['_id']) for item in query]
    
    header = (_(u'Name'),
              _(u'Type'),
              _(u'Registry number'),
              _(u'Serial number'),
              #_(u'Node chef id'),
              _(u'Id'))
    
    # Column widths in percentage
    widths = (20, 20, 20, 20, 20)
    title =  _(u'Computers report')
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        
    # Sort rows
    # TODO: Use MongoDB Collations to do a "ignore_case" sorting
    # (MongoDB 2.6 does not support "ignore case" sorting)   
    rows = sorted(rows, key = lambda i: (i[0].lower()))
        
    return {'headers': header,
            'rows': rows,
            'widths': widths,
            'default_order': [[ 0, 'asc' ]],
            'report_title': title,
            'page': _(u'Page'),
            'of': _(u'of'),
            'report_type': file_ext,
            'now': now}
