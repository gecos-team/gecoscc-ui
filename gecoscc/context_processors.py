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


from pyramid.events import NewRequest
from pyramid.events import subscriber

from gecoscc.version import __VERSION__ as GCCUI_VERSION


@subscriber(NewRequest)
def set_version(event):
    event.request.VERSION = GCCUI_VERSION
