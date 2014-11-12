import redis
import simplejson as json

from pyramid.response import Response
from pyramid.threadlocal import get_current_registry

from socketio import socketio_manage
from socketio.namespace import BaseNamespace
from socketio.server import SocketIOServer
from socketio.sgunicorn import GeventSocketIOWorker
from socketio.virtsocket import Socket

CHANNEL_WEBSOCKET = 'message'
TOKEN = 'token'


def get_manager():
    settings = get_current_registry().settings
    return redis.Redis(**settings['redis.conf'])


def is_websockets_enabled():
    settings = get_current_registry().settings
    return settings['server:main:worker_class'] == 'gecoscc.socks.GecosGeventSocketIOWorker'


def invalidate_change(request, schema_detail, objtype, objnew, objold):
    if not is_websockets_enabled():
        return

    manager = get_manager()
    manager.publish(CHANNEL_WEBSOCKET, json.dumps({
        'token': request.GET.get(TOKEN, ''),
        'action': 'change',
        'objectId': unicode(objnew['_id']),
        'user': request.user['username']
    }))


def invalidate_delete(request, schema_detail, objtype, obj):
    if not is_websockets_enabled():
        return

    manager = get_manager()
    manager.publish(CHANNEL_WEBSOCKET, json.dumps({
        'token': request.GET.get(TOKEN, ''),
        'action': 'delete',
        'objectId': unicode(obj['_id']),
        'user': request.user['username']
    }))


def invalidate_jobs(request, user=None):
    if not is_websockets_enabled():
        return

    user = user or request.user
    manager = get_manager()
    manager.publish(CHANNEL_WEBSOCKET, json.dumps({
        'username': user.get('username'),
        'action': 'jobs',
    }))

def update_tree():
    if not is_websockets_enabled():
        return

    manager = get_manager()
    manager.publish(CHANNEL_WEBSOCKET, json.dumps({
        'action': 'update_tree'
    }))


class GecosSocketIOServer(SocketIOServer):

    def get_socket(self, sessid=''):
        """Return an existing or new client Socket."""
        socket = self.sockets.get(sessid)

        if socket is None:
            socket = Socket(self, self.config)
            self.sockets[socket.sessid] = socket
        else:
            socket.incr_hits()

        return socket


class GecosGeventSocketIOWorker(GeventSocketIOWorker):

    server_class = GecosSocketIOServer


class GecosNamespace(BaseNamespace):

    def listener(self):
        if not is_websockets_enabled():
            return

        settings = get_current_registry().settings

        r = redis.StrictRedis(**settings['redis.conf'])
        r = r.pubsub()

        try:
            r.subscribe(CHANNEL_WEBSOCKET)

            for m in r.listen():
                if m['type'] == 'message':
                    data = json.loads(m['data'])
                    self.emit(CHANNEL_WEBSOCKET, data)
        except redis.ConnectionError:
            self.emit(CHANNEL_WEBSOCKET, {'redis':'error'})

    def on_subscribe(self, *args, **kwargs):
        self.spawn(self.listener)


def socketio_service(request):
    socketio_manage(request.environ,
                    {'': GecosNamespace},
                    request=request)
    return Response('no-data')
