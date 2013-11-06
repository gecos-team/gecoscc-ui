from cornice import Service
from copy import deepcopy


session_service = Service(name='session', path='/api/session/',
                          description='Logged user attributes')


@session_service.get()
def session_get(request):
    user = deepcopy(request.user)
    del user['password']
    del user['_id']
    return user
