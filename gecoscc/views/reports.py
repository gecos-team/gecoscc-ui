#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import logging
from xhtml2pdf import pisa
from pyramid_jinja2 import IJinja2Environment
from pyramid.threadlocal import get_current_registry
from bson import ObjectId
import csv
import os
import gecoscc

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO


from pyramid.view import view_config

logger = logging.getLogger(__name__)


class CSVRenderer(object):

    def __init__(self, info):
        pass

    def __call__(self, value, system):
        """ Returns a plain CSV-encoded string with content-type
        ``text/csv``. The content-type may be overridden by
        setting ``request.response.content_type``."""

        request = system.get('request')
        if request is not None:
            response = request.response
            ct = response.content_type
            if ct == response.default_content_type:
                response.content_type = 'text/csv'

        fout = StringIO()
        writer = csv.writer(fout, delimiter=',', quotechar='"', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(value.get('headers', []))
        writer.writerows(value.get('rows', []))
        return fout.getvalue()


def link_callback(uri, rel):
    """
    Convert HTML URIs to absolute system paths so xhtml2pdf can access those
    resources
    """
    # use short variable names
    sRoot = os.path.dirname(gecoscc.__file__)
    iUrl = '/static/images/'

    # convert URIs to absolute system paths
    if uri.startswith(iUrl):
        path = os.path.join(sRoot, uri.strip("/"))
    else:
        return uri  # handle absolute uri (ie: http://some.tld/foo.png)

    # make sure that file exists
    if not os.path.isfile(path):
            raise Exception(
                'image URI must start with %s' % (iUrl)
            )
    return path



# Para XML:
# https://pypi.org/project/PyramidXmlRenderer/

# Pruebo a generar un PDF

class PDFRenderer(object):

    def __init__(self, info):
        pass

    def __call__(self, value, system):
        """ Returns a PDF file """

        request = system.get('request')
        if request is not None:
            response = request.response
            ct = response.content_type
            if ct == response.default_content_type:
                response.content_type = 'application/pdf'


        jinja2_env = get_current_registry().queryUtility(IJinja2Environment)
        jinja2_template = jinja2_env.get_template('report.jinja2')
        html = jinja2_template.render(headers=value.get('headers', []),
                                      rows = value.get('rows', []),
                                      widths = value.get('widths', []),
                                      report_title = value.get('report_title', ''),
                                      page = value.get('page', ''),
                                      of = value.get('of', ''),
                                      report_type = value.get('report_type', ''))

        #logger.info("HTML=%s"%(html))
        
        fout = StringIO()
        pisa.CreatePDF(html, dest=fout, link_callback=link_callback)          

        return fout.getvalue()
        



@view_config(route_name='reports', renderer='templates/reports.jinja2',
             permission='edit')
def reports(context, request):
    ous = []
    
    # Get current user data
    is_superuser = request.user.get('is_superuser', False) 
    
    if not is_superuser:
        # Get visibles ous
        ou_visibles = request.user.get('ou_managed', []) + request.user.get('ou_readonly', [])
        for ou_id in ou_visibles:
            ou = request.db.nodes.find_one({'type': 'ou', '_id': ObjectId(ou_id) })
            if ou is not None:
                ous.append({'id': ou_id, 'name': ou['name']})
    
    return {'ou_managed': ous, 'is_superuser': is_superuser}    


def get_complete_path(db, path):
    '''
    Calculate the path with names instead of IDs.

    
    Args:
        db (mongodb)  : MongoDB reference.
        path (string) : Path of the node.

    Returns:
        compete_path (string) : Path width names instead of IDs
    '''
    
    complete_path = ''
    
    lpath = path.split(',')
    for idx, element in enumerate(lpath):
        if element == 'root':
            continue
        else:
            node = db.nodes.find_one({'_id': ObjectId(element)})
            if node is None:
               complete_path = 'Error path'
               break

            if idx == len(lpath)-1:
                complete_path += node['name'] 
            else:
                complete_path += node['name'] + ', '
         
    return complete_path

def get_html_node_link(node):
    '''
    Getting html tag link to node

    Args:
       node : MongoDB record
    	
    Returns:
       link : html tag link to node
    '''

    link = None
    path = node['path'].split(',')
    node_id = str(node['_id'])

    if len(path) > 1:
        parent_id = node['path'].split(',')[-1]
        href = '/#ou/{0}/{1}/{2}'.format(parent_id, node['type'], node_id)
        link = '<a href="{0}" onclick="return goto_parent_window(this);">{1}</a>'.format(href, node['name'])
  
    return link

def treatment_string_to_csv(item, key):
    none = u'--'
    logger.info("reports:::treatment_string_to_csv - item = {}".format(item))
    logger.info("reports:::treatment_string_to_csv - key = {}".format(key))
    return item.get(key, none).decode('utf-8') or none

def treatment_string_to_pdf(item, key, length):
    pdfstr = treatment_string_to_csv(item, key)
    if len(pdfstr) > length:
        pdfstr = pdfstr[0:length] + '...'
        
    return pdfstr 

