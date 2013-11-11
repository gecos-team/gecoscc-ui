from pyramid.security import remember, forget
from pyramid.httpexceptions import HTTPFound

from pyramid.view import view_config

from gecoscc.userdb import UserDoesNotExist
from gecoscc.i18n import _
from gecoscc.views import BaseView


@view_config(route_name='home', renderer='templates/home.jinja2')
def home(context, request):
    return {
    }


@view_config(route_name='sockjs_home', renderer='templates/sockjs/home.jinja2')
def sockjs_home(context, request):
    return {
    }


class LoginViews(BaseView):

    @view_config(route_name='sockjs_login', renderer='templates/sockjs/login.jinja2')
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
                        _("The requested username doesn't exists")),
                }

            if user is False:
                return {
                    'username': username,
                    'message': self.translate(_("The password doesn't match")),
                }

            headers = remember(self.request, username)
            self.request.session.flash(self.translate(
                _('welcome ${username}',
                  mapping={'username': user['username']})
            ))
            return HTTPFound(location=self.request.route_path('home'),
                             headers=headers)
        else:
            return {}

    @view_config(route_name='sockjs_logout', renderer='templates/sockjs/logout.jinja2')
    def logout(self):
        headers = forget(self.request)
        return HTTPFound(location=self.request.route_path('home'),
                         headers=headers)
