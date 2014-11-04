import datetime
import random

import redis
import simplejson as json

from socketio.namespace import BaseNamespace
from socketio import socketio_manage

td365 = datetime.timedelta(days=365)
td365seconds = int((td365.microseconds +
                    (td365.seconds + td365.days * 24 * 3600) * 10 ** 6) / 10 ** 6)


def get_manager(request):
    return redis.Redis()


def invalidate_change(request, schema_detail, objtype, objnew, objold):
    manager = get_manager(request)
    manager.publish('message', json.dumps({
        'action': 'change',
        'object': schema_detail().serialize(objnew)
    }))


def invalidate_delete(request, schema_detail, objtype, obj):
    manager = get_manager(request)
    manager.publish('message', json.dumps({
        'action': 'delete',
        'object': schema_detail().serialize(obj)
    }))


def invalidate_jobs(request):
    manager = get_manager(request)
    manager.publish('message', json.dumps({
        'action': 'jobs',
        'object': None
    }))


class GecosNamespace(BaseNamespace):

    # Crea el websocket

    def listener(self):
        r = redis.StrictRedis()
        r = r.pubsub()

        r.subscribe('message')

        for m in r.listen():
            if m['type'] == 'message':
                data = json.loads(m['data'])
                self.emit("message", data)

    def on_subscribe(self, *args, **kwargs):
        self.spawn(self.listener)

    def on_close(self, *args, **kwargs):
        pass

    # Fin Crea el websocket

    # Lee el post
    def on_message(self, msg):
        r = redis.Redis()
        r.publish('message', msg)


def socketio_service(request):
    retval = socketio_manage(request.environ,
                             {'': GecosNamespace},
                             request=request)

    return retval
