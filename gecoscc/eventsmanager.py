from pyramid.security import authenticated_userid

from pyramid_sockjs.session import Session

import logging
logger = logging.getLogger(__name__)

CHANNELS = {
    'admin': ('admin', ),
}


class EventsManager(Session):

    def on_open(self):
        self.send('Hello')
        self.manager.broadcast("Someone joined.")

    def on_message(self, message):
        userid = authenticated_userid(self.request)
        if userid is None:
            logger.warning("Unsecure message procedence!!!")
            return
        message = "{0}: {1}".format(userid, message)
        users = CHANNELS[userid]
        for session in self.manager.active_sessions():
            if (session.request.user and
                    session.request.user['username'] in users):
                session.send(message)
            else:
                logger.warning("Unsecure socket connection!!!")

    def on_close(self):
        self.manager.broadcast("Someone left.")
