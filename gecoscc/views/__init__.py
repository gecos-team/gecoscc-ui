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

from builtins import object
from pyramid.i18n import get_localizer


class BaseView(object):

    def __init__(self, context, request):
        self.context = context
        self.request = request
        self.translate = get_localizer(self.request).translate
