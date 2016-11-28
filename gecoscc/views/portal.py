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

import logging
import json

from pyramid.security import remember, forget, authenticated_userid
from pyramid.httpexceptions import HTTPFound
from pyramid.renderers import render
from pyramid.response import Response
from pyramid.view import view_config, forbidden_view_config
from pyramid.threadlocal import get_current_registry


from gecoscc.i18n import gettext as _
from gecoscc.messages import created_msg
from gecoscc.userdb import UserDoesNotExist
from gecoscc.socks import is_websockets_enabled
from gecoscc.views import BaseView
from gecoscc.command_util import get_setting
from gecoscc.models import PRINTER_TYPE
from gecoscc.models import PRINTER_CONN_TYPE
from gecoscc.models import PRINTER_OPPOLICY_TYPE


logger = logging.getLogger(__name__)


@view_config(route_name='home', renderer='templates/base_tree.jinja2',
             permission='edit')
def home(context, request):
    return {
        'websockets_enabled': json.dumps(is_websockets_enabled()),
        'update_error_interval': get_setting('update_error_interval', get_current_registry().settings, request.db),
        'printer_type': PRINTER_TYPE,
        'printer_conn_type': PRINTER_CONN_TYPE,
        'printer_oppolicy_type': PRINTER_OPPOLICY_TYPE
    }



class LoginViews(BaseView):

    @view_config(route_name='login', renderer='templates/login.jinja2')
    def login(self):
        if self.request.POST:
            username = self.request.POST.get('username')
            password = self.request.POST.get('password')
            try:
                user = self.request.userdb.login(username, password)
            except UserDoesNotExist:
                return {
                    'username': username,
                    'message': self.translate(
                        _("Please enter the correct username and password")),
                }

            if user is False:
                return {
                    'username': username,
                    'message': self.translate(_("Please enter the correct username and password")),
                }

            headers = remember(self.request, username)
            created_msg(self.request, self.translate(
                _('Welcome ${username}',
                  mapping={'username': user['username']})
            ), 'info')
            return HTTPFound(location=self.request.route_path('home'),
                             headers=headers)
        else:
            return {}

    @view_config(route_name='logout')
    def logout(self):
        headers = forget(self.request)
        return HTTPFound(location=self.request.route_path('login'),
                         headers=headers)


@forbidden_view_config()
@view_config(route_name='forbidden-view')
def forbidden_view(context, request):
    user = authenticated_userid(request)
    if user is not None:
        try:
            reason = context.explanation
        except AttributeError:
            reason = 'unknown'
        logger.debug("User %s tripped Forbidden view, request %s, "
                     "reason %s"%(str(user), str(request), str(reason)))
        response = Response(render('templates/forbidden.jinja2', {}))
        response.status_int = 403
        return response
    if user is None and (request.is_xhr or request.headers.get('content-type') == 'application/json'):
        response = Response(render('templates/forbidden.jinja2', {}))
        response.status_int = 403
        return response

    logger.debug("No user and forbidden access! --> redirect to login")        
    loginurl = request.route_url('login', _query=(('next', request.path),))
    return HTTPFound(location=loginurl)
