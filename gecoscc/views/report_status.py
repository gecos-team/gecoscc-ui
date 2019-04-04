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
import datetime
from datetime import timedelta

from gecoscc.views.reports import treatment_string_to_csv
from gecoscc.views.reports import treatment_string_to_pdf
from gecoscc.views.reports import get_html_node_link
from gecoscc.utils import get_filter_nodes_belonging_ou

from pyramid.view import view_config
from pyramid.httpexceptions import HTTPBadRequest
from pyramid.threadlocal import get_current_registry

from gecoscc.i18n import gettext as _

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
    is_superuser = request.user.get('is_superuser', False)
    ou = None 
    
    if not is_superuser:
        # Get managed ous
        ou_id = request.GET.get('ou_id', None)
        if ou_id is None:
            raise HTTPBadRequest()
        
        ou_visibles = request.user.get('ou_managed', []) + request.user.get('ou_readonly', [])
        if ou_id not in ou_visibles:
            raise HTTPBadRequest()

        ou = ou_id

    
    # Get user data
    query = None
    if is_superuser:
        query = request.db.nodes.find({'type': 'computer'}).sort('last_agent_run_time', -1)
    elif ou is not None:
        query = request.db.nodes.find(
            {'type': 'computer','path': get_filter_nodes_belonging_ou(ou)}).sort('last_agent_run_time', -1)
    else:
        raise HTTPBadRequest()
  
    rows = []

    current_time = int(time.time())
    logger.debug("report_status: current_time = {}".format(current_time))

    # update_error_interval: Hours. Converts it to seconds
    update_error_interval = timedelta(hours=int(get_current_registry().settings.get('update_error_interval', 24))).seconds
    logger.debug("report_status: update_error_interval = {}".format(update_error_interval))
    
    # gecos-agent runs every 60 minutes (cron resource: minutes 30)
    # See https://github.com/gecos-team/gecos-workstation-management-cookbook/blob/master/recipes/default.rb (line: 57)
    # 10-min max delay margin of chef-client concurrent executions
    # See https://github.com/gecos-team/gecosws-agent/blob/trusty/scripts/gecos-chef-client-wrapper (line: 30)
    # 15-min delay margin of network or chef-client execution
    # 60 + 10 + 15 = 85
    delay_margin = timedelta(minutes=85).seconds

    for item in query:
        row = []

        last_agent_run_time = int(item.get('last_agent_run_time',0))
        logger.debug("report_status: last_agent_run_time = {}".format(last_agent_run_time))

        if last_agent_run_time + delay_margin >= current_time:
            item['status'] = '<div class="centered" style="width: 100%"><img alt="OK" src="/static/images/checkmark.jpg"/></div>' \
                             if file_ext != 'csv' else 'OK'

        # Chef-run error or update_error_interval hours has elapsed from last agent run time
        elif (item['error_last_chef_client'] or
            last_agent_run_time + update_error_interval >= current_time
        ):
            item['status'] = '<div class="centered" style="width: 100%"><img alt="ERROR" src="/static/images/xmark.jpg"/></div>' \
                             if file_ext != 'csv' else 'ERROR'

        # delay_margin < last_agent_run_time < update_error_interval
        else:
            item['status'] = '<div class="centered" style="width: 100%"><img alt="WARN" src="/static/images/alertmark.jpg"/></div>' \
                             if file_ext != 'csv' else 'WARN'
        

        if file_ext == 'pdf':
            row.append(treatment_string_to_pdf(item, 'name', 20))
            row.append(item['_id'])

            if last_agent_run_time != 0:
                row.append(datetime.utcfromtimestamp(last_agent_run_time).strftime('%Y-%m-%d %H:%M:%S'))
            else:
                row.append(' -- ')

            row.append(item['status'])
        else:
            if file_ext == 'csv':
                row.append(treatment_string_to_csv(item, 'name'))
            else:
                row.append(get_html_node_link(item))
                row.append(item['_id'])
            if last_agent_run_time != 0:
                row.append(datetime.utcfromtimestamp(last_agent_run_time).strftime('%Y-%m-%d %H:%M:%S'))
            else:
                row.append('--')
            row.append(treatment_string_to_csv(item, 'status'))

        rows.append(row)
        
                
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

    now = datetime.datetime.now().strftime("%d/%m/%Y %H:%M")

    return {'headers': header,
            'rows': rows,
            'widths': widths,
            'report_title': title,
            'page': _(u'Page').encode('utf-8'),
            'of': _(u'of').encode('utf-8'),
            'report_type': file_ext,
            'now': now}
