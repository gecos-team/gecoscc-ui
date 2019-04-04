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

from gecoscc.views.reports import treatment_string_to_csv, treatment_string_to_pdf, get_complete_path, get_html_node_link, truncate_string_at_char
from gecoscc.utils import get_filter_nodes_belonging_ou
from gecoscc.tasks import ChefTask

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPBadRequest

from gecoscc.i18n import gettext as _

logger = logging.getLogger(__name__)


@view_config(route_name='report_file', renderer='csv',
             permission='edit',
             request_param=("type=storages", "format=csv"))
def report_storages_csv(context, request):
    filename = 'report_storages.csv'
    request.response.content_disposition = 'attachment;filename=' + filename    
    return report_storages(context, request, 'csv')

@view_config(route_name='report_file', renderer='pdf',
             permission='edit',
             request_param=("type=storages", "format=pdf"))
def report_storages_pdf(context, request):
    filename = 'report_storages.pdf'
    request.response.content_disposition = 'attachment;filename=' + filename    
    return report_storages(context, request, 'pdf')

@view_config(route_name='report_file', renderer='templates/report.jinja2',
             permission='edit',
             request_param=("type=storages", "format=html"))
def report_storages_html(context, request):
    return report_storages(context, request, 'html')


def report_storages(context, request, file_ext):
    '''
    Generate a report with all the storages and its related users.

    
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
    logger.debug("report_computer ::: ou_id = {}".format(ou_id))
    if ou_id is None:
        raise HTTPBadRequest()

    if not is_superuser: # Administrator: checks if ou is visible
        is_visible = ou_id in request.user.get('ou_managed', []) or \
                     ou_id in request.user.get('ou_readonly', [])
    else: # Superuser: only checks if exists
        is_visible = request.db.nodes.find_one({'_id': ObjectId(ou_id)})

    logger.debug("report_computer ::: is_visible = {}".format(is_visible))
    if not is_visible:
        raise HTTPBadRequest()
 
    # Get storages policy
    policy = request.db.policies.find_one({'slug': 'storage_can_view'})
    property_name = 'policies.' + str(policy['_id']) + '.object_related_list'
    
    # Get all storages
    query = request.db.nodes.find(
        {'type': 'storage','path': get_filter_nodes_belonging_ou(ou_id)})

    rows = []
    if file_ext == 'pdf':
        for item in query:
            row = []
            # No path in PDF because it's too long
            row.append('--')
            row.append(item['name'])
            row.append(item['uri'])
            row.append(item['_id'])
            
            # Get all nodes related with this storage
            nodes_query = request.db.nodes.find({property_name: str(item['_id'])})
            # Targets: ou, group or user
            users = []
            for node in nodes_query:
                if node['type'] == 'ou':
                    users = list(request.db.nodes.find(
                                    {'path': get_filter_nodes_belonging_ou(node['_id']),
                                    'type': 'user'}))
                elif node['type'] == 'group':
                    users = list(request.db.nodes.find(
                                    {'_id': node['members'], 
                                    'type': 'user'}))
                elif node['type'] == 'user':
                    users = [node]
                
            if len(users) == 0:
                row.append('--')
                row.append('--')                
                rows.append(row)
            else:
                for user in users:
                    user_row = list(row)
                    user_row.append(user['name'])
                    # No path in PDF because it's too long
                    user_row.append('--')
                    rows.append(user_row)

            
    else:
        for item in query:
            row = []
            item['complete_path'] = get_complete_path(request.db, item['path'])
            row.append(treatment_string_to_csv(item, 'complete_path'))
            if file_ext == 'csv':
                row.append(treatment_string_to_csv(item, 'name'))
            else: # html links
                row.append(get_html_node_link(item))
            row.append(treatment_string_to_csv(item, 'uri'))
            row.append(item['_id'])
            
            # Get all nodes related with this printer
            nodes_query = request.db.nodes.find({property_name: str(item['_id'])})
            # Targets: ou, group or user
            users = []
            for node in nodes_query:
                if node['type'] == 'ou':
                    users = list(request.db.nodes.find(
                                    {'path': get_filter_nodes_belonging_ou(node['_id']),
                                    'type': 'user'}))
                elif node['type'] == 'group':
                    users = list(request.db.nodes.find(
                                    {'_id': node['members'], 
                                    'type': 'user'}))
                elif node['type'] == 'user':
                    users = [node]
                
            if len(users) == 0:
                row.append('--')
                rows.append(row)
            else:
                for user in users:
                    user_row = list(row)
                    if file_ext == 'csv':
                        user_row.append(treatment_string_to_csv(user, 'name'))
                    else: # html links
                        user_row.append(get_html_node_link(user))
                    user['complete_path'] = get_complete_path(request.db, item['path'])
                    rows.append(user_row)
        
    
    header = (_(u'Path').encode('utf-8'),
              _(u'Name').encode('utf-8'),
              _(u'Uri').encode('utf-8'),
              _(u'Id').encode('utf-8'),
              _(u'User').encode('utf-8'))
    
    # Column widths in percentage
    widths = (0, 20, 45, 15, 20, 0)
    title =  _(u'Storages and related users report')
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        
    return {'headers': header,
            'rows': rows,
            'widths': widths,
            'report_title': title,
            'page': _(u'Page').encode('utf-8'),
            'of': _(u'of').encode('utf-8'),
            'report_type': file_ext,
            'now': now}
