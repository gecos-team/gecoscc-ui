from pyramid_sockjs import get_session_manager
import simplejson as json


def get_manager(request):
    return get_session_manager('sockjs', request.registry)


def invalidate_change(request, schema_detail, objtype, objnew, objold):
    manager = get_manager(request)
    manager.broadcast(json.dumps({
        'action': 'change',
        'object': schema_detail().serialize(objnew)
    }))


def invalidate_delete(request, schema_detail, objtype, obj):
    manager = get_manager(request)
    manager.broadcast(json.dumps({
        'action': 'delete',
        'object': schema_detail().serialize(obj)
    }))
