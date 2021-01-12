#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Alberto Beiztegui <albertobeiz@gmail.com>
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import logging

from six import text_type
from geventwebsocket.gunicorn.workers import GeventWebSocketWorker
from geventwebsocket.handler import WebSocketHandler

from pyramid.threadlocal import get_current_registry

CHANNEL_WEBSOCKET = 'message'
TOKEN = 'token'

logger = logging.getLogger(__name__)


def is_websockets_enabled():
    settings = get_current_registry().settings
    return (('server:main:worker_class' in settings) and 
        (settings['server:main:worker_class'] == 
            'gecoscc.socks.GecosGeventSocketIOWorker'))


def get_sio():
    settings = get_current_registry().settings
    return settings['sio']


def invalidate_change(request, objnew):
    if not is_websockets_enabled():
        logger.info("Websockets not enabled!")
        return

    sio = get_sio()
    sio.emit(CHANNEL_WEBSOCKET, {
        'token': request.GET.get(TOKEN, ''),
        'action': 'change',
        'objectId': text_type(objnew['_id']),
        'user': request.user['username']
    })


def invalidate_delete(request, obj):
    if not is_websockets_enabled():
        logger.info("Websockets not enabled!")
        return

    sio = get_sio()
    sio.emit(CHANNEL_WEBSOCKET, {
        'token': request.GET.get(TOKEN, ''),
        'action': 'delete',
        'objectId': text_type(obj['_id']),
        'path': obj['path'],
        'user': request.user['username']
    })


def invalidate_jobs(_request, user=None):
    if not is_websockets_enabled():
        logger.info("Websockets not enabled!")
        return

    sio = get_sio()
    sio.emit(CHANNEL_WEBSOCKET, {
        'username': user.get('username'),
        'action': 'jobs',
    })

def maintenance_mode(_request, msg):
    if not is_websockets_enabled():
        logger.info("Websockets not enabled!")
        return

    sio = get_sio()
    sio.emit(CHANNEL_WEBSOCKET, {
        'action': 'maintenance',
        'message': msg
    })
    
def update_tree(path = 'root'):
    if not is_websockets_enabled():
        logger.info("Websockets not enabled!")
        return

    sio = get_sio()
    sio.emit(CHANNEL_WEBSOCKET, {
        'action': 'update_tree',
        'path': path
    })


def add_computer_to_user(computer, user):
    if not is_websockets_enabled():
        logger.info("Websockets not enabled!")
        return

    sio = get_sio()
    sio.emit(CHANNEL_WEBSOCKET, {
        'action': 'add_computer_to_user',
        'computer': text_type(computer),
        'user': text_type(user)
    })

def delete_computer(object_id, path):
    if not is_websockets_enabled():
        logger.info("Websockets not enabled!")
        return

    sio = get_sio()
    sio.emit(CHANNEL_WEBSOCKET, {
        'token': '',
        'action': 'delete',
        'objectId': text_type(object_id),
        'path': path,
        'user': 'Chef server'
    })

def socktail(logdata):
    if not is_websockets_enabled():
        logger.info("Websockets not enabled!")
        return

    sio = get_sio()
    sio.emit('logdata', {
        'action': 'socktail',
        'logdata': text_type(logdata)
    },
    namespace='/tail')

class GecosWSGIHandler(WebSocketHandler):

    def get_environ(self):
        env = super(GecosWSGIHandler, self).get_environ()
        headers = dict(self._headers())
        if ('HTTP_X_FORWARDED_PROTO' in headers and 
            headers['HTTP_X_FORWARDED_PROTO'] == 'https'):
            env['wsgi.url_scheme'] = 'https'
        return env


class GecosGeventSocketIOWorker(GeventWebSocketWorker):
    wsgi_handler = GecosWSGIHandler
    
