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
        writer = csv.writer(fout, delimiter=',', quotechar=',', quoting=csv.QUOTE_MINIMAL)
        writer.writerow(value.get('headers', []))
        writer.writerows(value.get('rows', []))
        return fout.getvalue()




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
        pisa.CreatePDF(html, dest=fout)          

        return fout.getvalue()
        



@view_config(route_name='reports', renderer='templates/reports.jinja2',
             permission='edit')
def reports(context, request):
    ous = []
    
    # Get current user data
    is_superuser = request.user.get('is_superuser', False) 
    
    if not is_superuser:
        # Get managed ous
        ou_managed = request.user.get('ou_managed', [])
        for ou_id in  ou_managed:
            ou = request.db.nodes.find_one({'type': 'ou', '_id': ObjectId(ou_id) })
            if ou is not None:
                ous.append({'id': ou_id, 'name': ou['name']})
    
    return {'ou_managed': ous, 'is_superuser': is_superuser}    


def treatment_string_to_csv(item, key):
    none = '--'
    return item.get(key, none).encode('utf-8') or none


