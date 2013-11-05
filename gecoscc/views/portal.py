from pyramid.i18n import get_localizer
from pyramid.security import remember, forget
from pyramid.httpexceptions import HTTPFound

from pyramid.view import view_config

from gecoscc.userdb import UserDoesNotExist
from gecoscc.i18n import _


@view_config(route_name='home', renderer='templates/home.jinja2')
def home(context, request):
    return {
    }


class LoginViews(object):

    def __init__(self, context, request):
        self.context = context
        self.request = request
        self.translate = get_localizer(self.request).translate

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
                    'message': self.translate(_("The requested username doesn't exists")),
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

    @view_config(route_name='logout', renderer='templates/logout.jinja2')
    def logout(self):
        headers = forget(self.request)
        return HTTPFound(location=self.request.route_path('home'),
                         headers=headers)
