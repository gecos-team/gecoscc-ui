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
    is_superuser = request.user.get('is_superuser', False)
    ou = None 
    
    if not is_superuser:
        # Get managed ous
        ou_id = request.GET.get('ou_id', None)
        if ou_id is None:
            raise HTTPBadRequest()
        
        ou_managed = request.user.get('ou_managed', [])
        for oid in  ou_managed:
            if oid == ou_id:
                ou = ou_id
                    
    
    # Get user data
    query = None
    if is_superuser:
        query = request.db.nodes.find({'type': 'user'})
    elif ou is not None:
        query = request.db.nodes.find(
            {'type': 'user','path': get_filter_nodes_belonging_ou(ou)})
    else:
        raise HTTPBadRequest()
  
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