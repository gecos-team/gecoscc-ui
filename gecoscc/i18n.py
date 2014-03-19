from pyramid.events import NewRequest
from pyramid.events import subscriber
from pyramid.i18n import TranslationStringFactory
from pyramid.threadlocal import get_current_registry


TranslationString = TranslationStringFactory('gecoscc')


@subscriber(NewRequest)
def setAcceptedLanguagesLocale(event):
    if not event.request.accept_language:
        return
    accepted = event.request.accept_language
    settings = get_current_registry().settings
    default_locale_name = settings['pyramid.default_locale_name']
    event.request._LOCALE_ = accepted.best_match(('en', 'es'), default_locale_name)
