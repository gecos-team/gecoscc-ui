#
# Copyright 2018, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Jose M. Rodriguez <jmrodriguez@gruposolutia.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import logging
import datetime
from bson import ObjectId

from gecoscc.views.reports import treatment_string_to_csv
from gecoscc.views.reports import treatment_string_to_pdf, get_html_node_link
from gecoscc.utils import get_filter_nodes_belonging_ou
from gecoscc.tasks import ChefTask

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPBadRequest

from gecoscc.i18n import gettext as _


logger = logging.getLogger(__name__)


@view_config(route_name='report_file', renderer='csv',
             permission='edit',
             request_param=("type=no-user_computers", "format=csv"))
def report_no_user_computers_csv(context, request):
    filename = 'report_no-user_computers.csv'
    request.response.content_disposition = 'attachment;filename=' + filename
    return report_no_user_computers(context, request, 'csv')

@view_config(route_name='report_file', renderer='pdf',
             permission='edit',
             request_param=("type=no-user_computers", "format=pdf"))
def report_no_user_computers_pdf(context, request):
    filename = 'report_no-user_computers.pdf'
    request.response.content_disposition = 'attachment;filename=' + filename
    return report_no_user_computers(context, request, 'pdf')

@view_config(route_name='report_file', renderer='templates/report.jinja2',
             permission='edit',
             request_param=("type=no-user_computers", "format=html"))
def report_no_user_computers_html(context, request):
    return report_no_user_computers(context, request, 'html')


def report_no_user_computers(context, request, file_ext):
    '''
    Generate a report with all the no-user computers that belongs to a OU.
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

    # Get managed ous
    ou_id = request.GET.get('ou_id', None)
    logger.debug("report_no-user_computers ::: ou_id = {}".format(ou_id))
    if ou_id is None:
        raise HTTPBadRequest()

    if not is_superuser: # Administrator: checks if ou is visible
        is_visible = ou_id in request.user.get('ou_managed', []) or \
                     ou_id in request.user.get('ou_readonly', [])
    else: # Superuser: only checks if exists
        is_visible = request.db.nodes.find_one({'_id': ObjectId(ou_id)})

    logger.debug("report_no-user_computers ::: is_visible = {}".format(is_visible))
    if not is_visible:
        raise HTTPBadRequest()

    task = ChefTask()
    related_computers = []
    related_objects = []
    
    filters = ({'type': 'user','path': get_filter_nodes_belonging_ou(ou_id)})

    logger.info("report_no-user_computers: filters = {}".format(filters))

    users = request.db.nodes.find(filters)
    for user in users:
        related_computers = task.get_related_computers_of_user(user, related_computers, related_objects)

    references = [c['_id'] for c in related_computers]
    logger.info("report_no-user_computers: references = {}".format(references))
    filters2 = (
        {'type': 'computer'} if is_superuser
        else {'type': 'computer','path': get_filter_nodes_belonging_ou(ou_id)})

    filters2.update({'_id': {'$nin': [c['_id'] for c in related_computers]}})
    logger.info("report_no-user_computers: filters2 = {}".format(filters2))
    computers = request.db.nodes.find(filters2)

    rows = []
    
    if file_ext == 'pdf':
        rows = [(item['name'],
                 treatment_string_to_pdf(item, 'family', 15),
                 treatment_string_to_pdf(item, 'registry', 15),
                 treatment_string_to_pdf(item, 'serial', 20),
                 item['node_chef_id'],
                 item['_id']) for item in computers]
    else:
        rows = [(treatment_string_to_csv(item, 'name') if file_ext == 'csv' else get_html_node_link(item),
                 treatment_string_to_csv(item, 'family'),
                 treatment_string_to_csv(item, 'registry'),
                 treatment_string_to_csv(item, 'serial'),
                 treatment_string_to_csv(item, 'node_chef_id'),
                 item['_id']) for item in computers]

    header = (_(u'Name').encode('utf-8'),
              _(u'Type').encode('utf-8'),
              _(u'Registry number').encode('utf-8'),
              _(u'Serial number').encode('utf-8'),
              _(u'Node chef id').encode('utf-8'),
              _(u'Id').encode('utf-8'))
    
    # Column widths in percentage
    widths = (25, 10, 15, 15, 20, 15)
    title =  _(u'No-user computers')
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        
        
    return {'headers': header,
            'rows': rows,
            'widths': widths,
            'report_title': title,
            'page': _(u'Page').encode('utf-8'),
            'of': _(u'of').encode('utf-8'),
            'report_type': file_ext,
            'now': now}
