#
# Copyright 2018, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Abraham Macias <amp_21004@yahoo.es>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#


from builtins import object
from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest
from pyramid.view import view_config
from bson import ObjectId

import logging
logger = logging.getLogger(__name__)

class TXTRenderer(object):

    def __init__(self, info):
        pass

    def __call__(self, value, system):
        """ Returns a plain text string with content-type
        ``text/plain``. The content-type may be overridden by
        setting ``request.response.content_type``."""

        request = system.get('request')
        if request is not None:
            response = request.response
            response.content_type = 'text/plain'
            response.content_encoding = value.get('encoding', '')
            response.content_length = len(value.get('data', ''))

        return value.get('data', '')




@view_config(route_name='download_computer_logs', renderer='txt',
             permission='edit')
def download_log_file(context, request):
    filename = request.matchdict.get('filename')
    if filename is None:
        logging.error('/download/computer/logs: filename is None')
        raise HTTPBadRequest()
        
    request.response.content_disposition = 'attachment;filename=' + filename
    return get_log_file(context, request)



@view_config(route_name='computer_logs', renderer='txt',
             permission='edit')
def get_log_file(context, request):
    node_id = request.matchdict.get('node_id')
    filename = request.matchdict.get('filename')
    if node_id is None:
        logging.error('/computer/logs: node_id is None')
        raise HTTPBadRequest()


    if filename is None:
        logging.error('/computer/logs: filename is None')
        raise HTTPBadRequest()
    
    
    logging.info('/computer/logs: node_id=%s filename=%s'%(node_id, filename))
    
    computer = request.db.nodes.find_one({'_id': ObjectId(node_id), 'type': 'computer'}, {"logs": True})
    if not computer:
        logging.error('/computer/logs: computer not found with node_id=%s'%(node_id))
        raise HTTPNotFound()

    data = ''    
    if ('logs' in computer and 
        'files' in computer['logs'] and 
        len(computer['logs']['files'])>0):
        
        fdata = None
        for filedata in computer['logs']['files']:
            if filedata['filename'] == filename:
                fdata = filedata
                break
        
        data = fdata['content']
        
    else:
        logging.error('/computer/logs: log file not found: %s'%(filename))
        raise HTTPNotFound()
        
    return {'encoding': 'utf-8',
            'data': data}


@view_config(request_method='DELETE', renderer='json', 
             route_name='delete_computer_logs', permission='edit')
def delete_log_file(context, request):
    node_id = request.matchdict.get('node_id')
    filename = request.matchdict.get('filename')
    if node_id is None:
        logging.error('/delete/computer/logs: node_id is None')
        raise HTTPBadRequest()


    if filename is None:
        logging.error('/delete/computer/logs: filename is None')
        raise HTTPBadRequest()
    
    
    logging.info('/delete/computer/logs: node_id=%s filename=%s'%(node_id, filename))
    
    computer = request.db.nodes.find_one({'_id': ObjectId(node_id), 'type': 'computer'}, {"logs": True})
    if not computer:
        logging.error('/computer/logs: computer not found with node_id=%s'%(node_id))
        raise HTTPNotFound()

    if ('logs' in computer and 
        'files' in computer['logs'] and 
        len(computer['logs']['files'])>0):

        fdata = None
        for filedata in computer['logs']['files']:
            if filedata['filename'] == filename:
                fdata = filedata
                break
        
        if fdata is not None:
            computer['logs']['files'].remove(fdata)
            
        if len(computer['logs']['files']) > 0:
            # Remove only a log
            request.db.nodes.update_one({'_id': ObjectId(node_id), 'type': 'computer'}, {'$pull': { "logs.files":  { 'filename': filename }}})
        
        else:
            # Remove all log information
            request.db.nodes.update_one({'_id': ObjectId(node_id), 'type': 'computer'}, {'$unset': { "logs": "" }})
        
        
        
    else:
        logging.error('/delete/computer/logs: log file not found: %s'%(filename))
        raise HTTPNotFound()
        
    return {'ok': True, 'message': 'Content deleted'}
