from pyramid.security import remember, forget
from pyramid.httpexceptions import HTTPFound

from pyramid.view import view_config

from gecoscc.userdb import UserDoesNotExist
from gecoscc.i18n import _
from gecoscc.views import BaseView


@view_config(route_name='home', renderer='templates/home.jinja2')
def home(context, request):
    return {}


@view_config(route_name='admins', renderer='templates/admins.jinja2')
def admins(context, request):
    return {}


@view_config(route_name='groups', renderer='templates/groups.jinja2')
def groups(context, request):
    return {}


@view_config(route_name='reports', renderer='templates/reports.jinja2')
def reports(context, request):
    return {}


#;;;;;;;;;;;
# TO DELETE
#;;;;;;;;;;;
@view_config(route_name='users', renderer='templates/to_delete/users.jinja2')
def users(context, request):
    return {}


@view_config(route_name='ous', renderer='templates/to_delete/ous.jinja2')
def ous(context, request):
    return {}


@view_config(route_name='policies_wallpaper', renderer='templates/to_delete/policies-wallpaper.jinja2')
def policies_wallpaper(context, request):
    return {}


@view_config(route_name='policies_software', renderer='templates/to_delete/policies-software.jinja2')
def policies_software(context, request):
    return {}


@view_config(route_name='policies_storage', renderer='templates/to_delete/policies-storage.jinja2')
def policies_storage(context, request):
    return {}


@view_config(route_name='computers', renderer='templates/to_delete/computers.jinja2')
def computers(context, request):
    return {}


@view_config(route_name='printers', renderer='templates/to_delete/printers.jinja2')
def printers(context, request):
    return {}
#;;;;;;;;;;;;;;;
# END TO DELETE
#;;;;;;;;;;;;;;;


@view_config(route_name='sockjs_home', renderer='templates/sockjs/home.jinja2')
def sockjs_home(context, request):
    return {
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

    @view_config(route_name='logout')
    def logout(self):
        headers = forget(self.request)
        return HTTPFound(location=self.request.route_path('login'),
                         headers=headers)
