from pyramid.view import view_config
from pyramid.security import authenticated_userid


from gecoscc.views import BaseView


class EventsViews(BaseView):

    @view_config(route_name='sockjs_message', renderer='json')
    def message(self):
        message = self.request.POST.get('message')
        apikey = self.request.POST.get('apikey')
        username = None
        if apikey:
            user = self.request.userdb.get_user_by_apikey(apikey)
            if user:
                username = user['username']
        else:
            username = authenticated_userid(self.request)

        if username is None:
            return {
                'status': 'bad',
                'errormsg': 'User not logged',
            }
        if message:
            manager = self.request.get_sockjs_manager('sockjs')
            for session in manager.active_sessions():
                if (session.request.user and
                        session.request.user['username'] == username):
                    session.on_message(message)
                    break

        return {
            'status': 'ok',
        }
