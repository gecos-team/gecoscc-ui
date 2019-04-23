from beaker.session import SessionObject, Session
from pyramid_beaker import coerce_session_params
from gecoscc.eventsmanager import ExpiredSessionEvent
from pyramid.settings import asbool
from zope.interface import implementer
from pyramid.interfaces import ISession
from pyramid.threadlocal import get_current_registry

import time
import logging
logger = logging.getLogger(__name__)

class GecosSession(Session):
    """
        Gecos session reuses pyramid beaker session; besides,
        it launches expired session event
    """
    def __init__(self, *args, **kwargs):
        self.request_object = kwargs.pop('request_object')
        Session.__init__(self, *args, **kwargs)

    # Overrides method   
    def load(self):
        "Loads the data from this session from persistent storage"
        self.namespace = self.namespace_class(self.id,
            data_dir=self.data_dir,
            digest_filenames=False,
            **self.namespace_args)
        now = time.time()
        if self.use_cookies:
            self.request['set_cookie'] = True

        self.namespace.acquire_read_lock()
        timed_out = False
        try:
            self.clear()
            try:
                session_data = self.namespace['session']

                if (session_data is not None and self.encrypt_key):
                    session_data = self._decrypt_data(session_data)

                # Memcached always returns a key, its None when its not
                # present
                if session_data is None:
                    session_data = {
                        '_creation_time': now,
                        '_accessed_time': now
                    }
                    self.is_new = True
            except (KeyError, TypeError):
                session_data = {
                    '_creation_time': now,
                    '_accessed_time': now
                }
                self.is_new = True

            if session_data is None or len(session_data) == 0:
                session_data = {
                    '_creation_time': now,
                    '_accessed_time': now
                }
 
                self.is_new = True

            if self.timeout is not None and \
                now - session_data['_accessed_time'] > self.timeout:

                try:
                    user = dict({'username':session_data['auth.userid']})
                    setattr(self.request_object, 'user', user)
                    get_current_registry().notify(ExpiredSessionEvent(self.request_object))
                except (KeyError, TypeError):
                    pass
                timed_out = True
            else:
                # Properly set the last_accessed time, which is different
                # than the *currently* _accessed_time
                if self.is_new or '_accessed_time' not in session_data:
                    self.last_accessed = None
                else:
                    self.last_accessed = session_data['_accessed_time']

                # Update the current _accessed_time
                session_data['_accessed_time'] = now

                # Set the path if applicable
                if '_path' in session_data:
                    self._path = session_data['_path']
                self.update(session_data)
                self.accessed_dict = session_data.copy()
        finally:
            self.namespace.release_read_lock()
        if timed_out:
            self.invalidate()

class GecosSessionObject(SessionObject):
    def __init__(self, environ, **params):
        SessionObject.__init__(self, environ, **params)

    # Overrides method
    def _session(self):
        """Lazy initial creation of session object"""
        if self.__dict__['_sess'] is None:
            params = self.__dict__['_params']
            environ = self.__dict__['_environ']
            self.__dict__['_headers'] = req = {'cookie_out': None}
            req['cookie'] = environ.get('HTTP_COOKIE')
            session_cls = params.get('session_class', None)
            if session_cls is None:
                if params.get('type') == 'cookie':
                    session_cls = CookieSession
                else:
                    session_cls = GecosSession
            else:
                assert issubclass(session_cls, MySession),\
                    "Not a Session: " + session_cls
            self.__dict__['_sess'] = session_cls(req, **params)
        return self.__dict__['_sess']


def GecosSessionFactoryConfig(**options):
    class PyramidGecosSessionObject(GecosSessionObject):
        _options = options
        _cookie_on_exception = _options.pop('cookie_on_exception', True)
        def __init__(self, request):
            self._options['request_object'] = request
            GecosSessionObject.__init__(self, request.environ, **self._options)
            def session_callback(request, response):
                exception = getattr(request, 'exception', None)
                if (exception is None or self._cookie_on_exception
                    and self.accessed()):
                    self.persist()
                    headers = self.__dict__['_headers']
                    if headers['set_cookie'] and headers['cookie_out']:
                        response.headerlist.append(
                            ('Set-Cookie', headers['cookie_out']))
            request.add_response_callback(session_callback)
        # ISession API

        @property
        def new(self):
            return self.last_accessed is None

        changed = GecosSessionObject.save

        # modifying dictionary methods

        @call_save
        def clear(self):
            return self._session().clear()

        @call_save
        def update(self, d, **kw):
            return self._session().update(d, **kw)

        @call_save
        def setdefault(self, k, d=None):
            return self._session().setdefault(k, d)

        @call_save
        def pop(self, k, d=None):
            return self._session().pop(k, d)

        @call_save
        def popitem(self):
            return self._session().popitem()

        __setitem__ = call_save(GecosSessionObject.__setitem__)
        __delitem__ = call_save(GecosSessionObject.__delitem__)

        # Flash API methods
        def flash(self, msg, queue='', allow_duplicate=True):
            storage = self.setdefault('_f_' + queue, [])
            if allow_duplicate or (msg not in storage):
                storage.append(msg)

        def pop_flash(self, queue=''):
            storage = self.pop('_f_' + queue, [])
            return storage

        def peek_flash(self, queue=''):
            storage = self.get('_f_' + queue, [])
            return storage

        # CSRF API methods
        def new_csrf_token(self):
            token = hexlify(os.urandom(20))
            self['_csrft_'] = token
            return token

        def get_csrf_token(self):
            token = self.get('_csrft_', None)
            if token is None:
                token = self.new_csrf_token()
            return token

    return implementer(ISession)(PyramidGecosSessionObject)

def call_save(wrapped):
    """ By default, in non-auto-mode beaker badly wants people to
    call save even though it should know something has changed when
    a mutating method is called.  This hack should be removed if
    Beaker ever starts to do this by default. """
    def save(session, *arg, **kw):
        value = wrapped(session, *arg, **kw)
        session.save()
        return value
    save.__doc__ = wrapped.__doc__
    return save

def session_factory_from_settings(settings):
    """ Return a Pyramid session factory using Beaker session settings
    supplied from a Paste configuration file"""
    prefixes = ('session.', 'beaker.session.')
    options = {}

    # Pull out any config args meant for beaker session. if there are any
    for k, v in settings.items():
        for prefix in prefixes:
            if k.startswith(prefix):
                option_name = k[len(prefix):]
                if option_name == 'cookie_on_exception':
                    v = asbool(v)
                options[option_name] = v

    options = coerce_session_params(options)
    return GecosSessionFactoryConfig(**options)

