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
import time
from datetime import datetime, timedelta

from gecoscc.views.reports import (treatment_string_to_csv,
    treatment_string_to_pdf, get_html_node_link, check_visibility_of_ou)
from gecoscc.utils import get_filter_nodes_belonging_ou

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.threadlocal import get_current_registry

from gecoscc.i18n import gettext as _
import pymongo

logger = logging.getLogger(__name__)


@view_config(route_name='report_file', renderer='csv',
             permission='edit',
             request_param=("type=status", "format=csv"))
def report_status_csv(context, request):
    filename = 'report_status.csv'
    request.response.content_disposition = 'attachment;filename=' + filename
    return report_status(context, request, 'csv')

@view_config(route_name='report_file', renderer='pdf',
             permission='edit',
             request_param=("type=status", "format=pdf"))
def report_status_pdf(context, request):
    filename = 'report_status.pdf'
    request.response.content_disposition = 'attachment;filename=' + filename
    return report_status(context, request, 'pdf')

@view_config(route_name='report_file', renderer='templates/report.jinja2',
             permission='edit',
             request_param=("type=status", "format=html"))
def report_status_html(context, request):
    return report_status(context, request, 'html')


def report_status(context, request, file_ext):
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
        {'type': 'computer','path': get_filter_nodes_belonging_ou(ou_id)}
        ).sort(
        [('error_last_chef_client', pymongo.DESCENDING),
         ('last_agent_run_time', pymongo.DESCENDING),
         ('name', pymongo.ASCENDING) ] )
  
    rows = []
    orders = []

    current_time = int(time.time())
    logger.debug("report_status: current_time = {}".format(current_time))

    # update_error_interval: Hours. Converts it to seconds
    update_error_interval = timedelta(
        hours=int(get_current_registry().settings.get(
            'update_error_interval', 24))).seconds
    logger.debug("report_status: update_error_interval = {}".format(
        update_error_interval))
    
    # gecos-agent runs every 60 minutes (cron resource: minutes 30)
    # See https://github.com/gecos-team/gecos-workstation-management-cookbook/blob/master/recipes/default.rb (line: 57)
    # 10-min max delay margin of chef-client concurrent executions
    # See https://github.com/gecos-team/gecosws-agent/blob/trusty/scripts/gecos-chef-client-wrapper (line: 30)
    # 15-min delay margin of network or chef-client execution
    # 60 + 10 + 15 = 85
    delay_margin = timedelta(minutes=85).seconds

    for item in query:
        row = []
        order = []
        status = '0'

        last_agent_run_time = int(item.get('last_agent_run_time',0))
        logger.debug("report_status: last_agent_run_time = {}".format(
            last_agent_run_time))

        if last_agent_run_time + delay_margin >= current_time:
            item['status'] = '<div class="centered" style="width: 100%">'\
                '<img alt="OK" src="/static/images/checkmark.jpg"/></div>' \
                    if file_ext != 'csv' else 'OK'

            status = '0'
        # Chef-run error or update_error_interval hours has elapsed from last agent run time
        elif (item['error_last_chef_client'] or
            last_agent_run_time + update_error_interval >= current_time
        ):
            item['status'] = '<div class="centered" style="width: 100%">'\
                '<img alt="ERROR" src="/static/images/xmark.jpg"/></div>' \
                    if file_ext != 'csv' else 'ERROR'
            status = '2'

        # delay_margin < last_agent_run_time < update_error_interval
        else:
            item['status'] = '<div class="centered" style="width: 100%">'\
                '<img alt="WARN" src="/static/images/alertmark.jpg"/></div>' \
                    if file_ext != 'csv' else 'WARN'
            status = '1'
        

        if file_ext == 'pdf':
            row.append(treatment_string_to_pdf(item, 'name', 20))
            order.append('')
            row.append(item['_id'])
            order.append('')

            if last_agent_run_time != 0:
                row.append(datetime.utcfromtimestamp(
                    last_agent_run_time).strftime('%d/%m/%Y %H:%M:%S'))
            else:
                row.append(' -- ')
            order.append(last_agent_run_time)

            row.append(item['status'])
            order.append(status)
        else:
            if file_ext == 'csv':
                row.append(treatment_string_to_csv(item, 'name'))
            else:
                row.append(get_html_node_link(item))
            order.append('')
            row.append(item['_id'])
            order.append('')
            if last_agent_run_time != 0:
                row.append(datetime.utcfromtimestamp(
                    last_agent_run_time).strftime('%d/%m/%Y %H:%M:%S'))
            else:
                row.append('--')
            order.append(last_agent_run_time)
            row.append(treatment_string_to_csv(item, 'status'))
            order.append(status)

        rows.append(row)
        orders.append(order)
        
                
    header = (_(u'Name').encode('utf-8'),
              _(u'Id').encode('utf-8'),
              _(u'Agent last runtime').encode('utf-8'),
              _(u'Status').encode('utf-8'))

    # Column widths in percentage
    if file_ext == 'pdf':
        widths = (45, 20, 20, 15)
    else:
        widths = (15, 35, 15, 20)

    title =  _(u'Computer with anomalies')

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    return {'headers': header,
            'rows': rows,
            'orders': orders,
            'default_order': [[ 3, 'desc' ], [ 2, 'desc' ], [ 0, 'asc' ]],
            'widths': widths,
            'report_title': title,
            'page': _(u'Page').encode('utf-8'),
            'of': _(u'of').encode('utf-8'),
            'report_type': file_ext,
            'now': now}
