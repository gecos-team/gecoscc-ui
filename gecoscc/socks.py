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


def cors_headers(request):
    origin = request.environ.get("HTTP_ORIGIN", '*')
    if origin == 'null':
        origin = '*'
    ac_headers = request.environ.get('HTTP_ACCESS_CONTROL_REQUEST_HEADERS')
    if ac_headers is not None:
        return (('access-control-allow-origin', origin),
                ('access-control-allow-credentials', 'true'),
                ('access-control-allow-headers', ac_headers))
    else:
        return (('access-control-allow-origin', origin),
                ('access-control-allow-credentials', 'true'))


def session_cookie(request):
    cookie = request.cookies.get('JSESSIONID')

    if not cookie:
        cookie = 'dummy'

    request.response.set_cookie('JSESSIONID', cookie)
    return ('Set-Cookie', request.response.headers['Set-Cookie'])


def cache_headers(request):
    d = datetime.now() + td365

    return (
        ('Access-Control-Max-Age', td365seconds),
        ('Cache-Control', 'max-age=%d, public' % td365seconds),
        ('Expires', d.strftime('%a, %d %b %Y %H:%M:%S')),
    )


def sock_info(request):
    response = request.response
    response.content_type = 'application/json; charset=UTF-8'
    response.headerlist.append(
        ('Cache-Control', 'no-store, no-cache, must-revalidate, max-age=0'))
    response.headerlist.extend(cors_headers(request))

    if request.method == 'OPTIONS':
        session_cookie(request)
        response.status = 204
        response.headerlist.append(
            ("Access-Control-Allow-Methods", "OPTIONS, GET"))
        response.headerlist.extend(cache_headers(request))
        return response
    info = {'entropy': random.randint(1, 2147483647),
            'websocket': 'socketio' not in request.environ,  #TODO: Comprobar esto
            'cookie_needed': True,
            'origins': ['*:*']}
    response.body = json.dumps(info)
    return response


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

    def on_open(self, *args, **kwargs):
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
