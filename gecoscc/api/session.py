#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Antonio Perez-Aranda <ant30tx@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

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
