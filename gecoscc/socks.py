import redis
import simplejson as json

from pyramid.response import Response

from socketio import socketio_manage
from socketio.namespace import BaseNamespace
from socketio.server import SocketIOServer
from socketio.sgunicorn import GeventSocketIOWorker
from socketio.virtsocket import Socket

CHANNEL_WEBSOCKET = 'message'
TOKEN = 'token'
USERNAME = 'gcc_username'


def get_manager(request):
    return redis.Redis()


def invalidate_change(request, schema_detail, objtype, objnew, objold):
    manager = get_manager(request)
    manager.publish(CHANNEL_WEBSOCKET, json.dumps({
        'token': request.GET.get(TOKEN, ''),
        'action': 'change',
        'objectId': unicode(objnew['_id']),
        'user': request.user['username']
    }))


def invalidate_delete(request, schema_detail, objtype, obj):
    manager = get_manager(request)
    manager.publish(CHANNEL_WEBSOCKET, json.dumps({
        'token': request.GET.get(TOKEN, ''),
        'action': 'delete',
        'objectId': unicode(obj['_id']),
        'user': request.user['username']
    }))


def invalidate_jobs(request):
    manager = get_manager(request)
    manager.publish(CHANNEL_WEBSOCKET, json.dumps({
        'username': request.POST.get(USERNAME),
        'action': 'jobs',
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
        r = redis.StrictRedis()
        r = r.pubsub()

        r.subscribe(CHANNEL_WEBSOCKET)

        for m in r.listen():
            if m['type'] == 'message':
                data = json.loads(m['data'])
                self.emit(CHANNEL_WEBSOCKET, data)

    def on_subscribe(self, *args, **kwargs):
        self.spawn(self.listener)


def socketio_service(request):
    socketio_manage(request.environ,
                    {'': GecosNamespace},
                    request=request)
    return Response('no-data')
