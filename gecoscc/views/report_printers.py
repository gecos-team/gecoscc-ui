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

from builtins import str
import logging
import datetime

from gecoscc.views.reports import (treatment_string_to_csv,
    treatment_string_to_pdf, get_complete_path, get_html_node_link,
    check_visibility_of_ou)
from gecoscc.utils import get_filter_nodes_belonging_ou
from gecoscc.tasks import ChefTask

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPBadRequest

from gecoscc.i18n import gettext as _

logger = logging.getLogger(__name__)


@view_config(route_name='report_file', renderer='csv',
             permission='edit',
             request_param=("type=printers", "format=csv"))
def report_printers_csv(context, request):
    filename = 'report_printers.csv'
    request.response.content_disposition = 'attachment;filename=' + filename    
    return report_printers(context, request, 'csv')

@view_config(route_name='report_file', renderer='pdf',
             permission='edit',
             request_param=("type=printers", "format=pdf"))
def report_printers_pdf(context, request):
    filename = 'report_printers.pdf'
    request.response.content_disposition = 'attachment;filename=' + filename    
    return report_printers(context, request, 'pdf')

@view_config(route_name='report_file', renderer='templates/report.jinja2',
             permission='edit',
             request_param=("type=printers", "format=html"))
def report_printers_html(context, request):
    return report_printers(context, request, 'html')


def report_printers(context, request, file_ext):
    '''
    Generate a report with all the printers and its related computers.

    
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

    # Get printers policy
    policy = request.db.policies.find_one({'slug': 'printer_can_view'})
    property_name = 'policies.' + str(policy['_id']) + '.object_related_list'
    
    # Get all printers
    query = request.db.nodes.find(
        {'type': 'printer', 'path': get_filter_nodes_belonging_ou(ou_id)})

    task = ChefTask()

    rows = []
    if file_ext == 'pdf':
        for item in query:
            row = []
            # No path in PDF because it's too long
            row.append('--')
            row.append(item['name']);
            row.append(treatment_string_to_pdf(item, 'manufacturer', 15))
            row.append(treatment_string_to_pdf(item, 'model', 15))
            row.append(treatment_string_to_pdf(item, 'serial', 15))
            row.append(treatment_string_to_pdf(item, 'registry', 15))

            # Get all nodes related with this printer
            nodes_query = request.db.nodes.find(
                {property_name: str(item['_id'])})
            related_computers = []
            related_objects = []
            for node in nodes_query:
                related_computers = task.get_related_computers(
                    node, related_computers, related_objects)
            
            # Remove duplicated computers
            computer_paths = []
            computers = []
            for computer in related_computers:
                full_path = computer['path'] + '.' + computer['name']
                if not full_path in computer_paths:
                    computer_paths.append(full_path)
                    computers.append(computer)
            
            if len(computers) == 0:
                row.append('--')
                rows.append(row)
            else:
                for computer in computers:
                    computer_row = list(row)
                    computer_row.append(treatment_string_to_pdf(
                        computer, 'name', 15))
                    # No path in PDF because it's too long
                    rows.append(computer_row)

            
    else:
        for item in query:
            row = []
            item['complete_path'] = get_complete_path(request.db, item['path'])
            row.append(treatment_string_to_csv(item, 'complete_path'))
            row.append(treatment_string_to_csv(item, 'name') \
                if file_ext == 'csv' else get_html_node_link(item))
            row.append(treatment_string_to_csv(item, 'manufacturer'))
            row.append(treatment_string_to_csv(item, 'model'))
            row.append(treatment_string_to_csv(item, 'serial'))
            row.append(treatment_string_to_csv(item, 'registry'))

            # Get all nodes related with this printer
            nodes_query = request.db.nodes.find(
                {property_name: str(item['_id'])})
            related_computers = []
            related_objects = []
            for node in nodes_query:
                related_computers = task.get_related_computers(
                    node, related_computers, related_objects)

            # Remove duplicated computers
            computer_paths = []
            computers = []
            for computer in related_computers:
                full_path = computer['path'] + '.' + computer['name']
                if not full_path in computer_paths:
                    computer_paths.append(full_path)
                    computers.append(computer)

                
            if len(computers) == 0:
                row.append('--')
                rows.append(row)
            else:
                for computer in computers:
                    computer_row = list(row)
                    computer_row.append(treatment_string_to_csv(
                        computer, 'name') \
                            if file_ext == 'csv' \
                            else get_html_node_link(computer))
                    computer['complete_path'] = get_complete_path(
                        request.db, item['path'])
                    rows.append(computer_row)
        
    
    header = (_(u'Path').encode('utf-8'),
              _(u'Name').encode('utf-8'),
              _(u'Manufacturer').encode('utf-8'),
              _(u'Model').encode('utf-8'),
              _(u'Serial number').encode('utf-8'),
              _(u'Registry number').encode('utf-8'),
              _(u'Computer').encode('utf-8'))
    
    # Column widths in percentage
    if file_ext == 'pdf':
        widths = (0, 25, 15, 15, 15, 15, 15)
    else:
        widths = (0, 20, 10, 10, 10, 10, 20)
    title =  _(u'Printers and related computers report')
    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")
        
    # Sort rows
    rows = sorted(rows, key = lambda i: (i[0].lower(), i[1].lower(),
                                         i[6].lower()))   
        
    return {'headers': header,
            'rows': rows,
            'default_order': [[ 0, 'asc' ], [ 1, 'asc' ], [ 6, 'asc' ]],
            'widths': widths,
            'report_title': title,
            'page': _(u'Page').encode('utf-8'),
            'of': _(u'of').encode('utf-8'),
            'report_type': file_ext,
            'now': now}
