#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

def created_msg(request, msg, msg_type):
    if not 'messages' in request.session:
        request.session['messages'] = []
    request.session['messages'].append((msg_type, msg))
