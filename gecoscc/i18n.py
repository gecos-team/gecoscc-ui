from pyramid.events import NewRequest
from pyramid.events import subscriber
from pyramid.i18n import TranslationStringFactory


TranslationString = TranslationStringFactory('gecoscc')


@subscriber(NewRequest)
def setAcceptedLanguagesLocale(event):
    if not event.request.accept_language:
        return
    accepted = event.request.accept_language
    event.request._LOCALE_ = accepted.best_match(('en', 'es'), 'en')
