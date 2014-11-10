import redis
import simplejson as json

from pyramid.response import Response

from socketio.namespace import BaseNamespace
from socketio import socketio_manage


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
        'object': schema_detail().serialize(objnew)
    }))


def invalidate_delete(request, schema_detail, objtype, obj):
    manager = get_manager(request)
    manager.publish(CHANNEL_WEBSOCKET, json.dumps({
        'token': request.GET.get(TOKEN, ''),
        'action': 'delete',
        'object': schema_detail().serialize(obj)
    }))


def invalidate_jobs(request):
    manager = get_manager(request)
    manager.publish(CHANNEL_WEBSOCKET, json.dumps({
        'token': request.POST.get(USERNAME),
        'action': 'jobs',
        'object': None
    }))


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
