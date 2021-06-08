#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from pyramid.events import NewRequest
from pyramid.events import subscriber
from pyramid.i18n import TranslationStringFactory, get_localizer
from pyramid.threadlocal import get_current_registry, get_current_request

TranslationString = TranslationStringFactory('gecoscc')


@subscriber(NewRequest)
def setAcceptedLanguagesLocale(event):
    if not event.request.accept_language:
        return
    accepted = event.request.accept_language
    settings = get_current_registry().settings
    default_locale_name = settings['pyramid.default_locale_name']
    locales = settings['pyramid.locales']
    event.request._LOCALE_ = accepted.best_match(locales, default_locale_name)


@subscriber(NewRequest)
def add_localizer(event):
    request = event.request
    localizer = get_localizer(request)

    def auto_translate(string, *args, **kwargs):
        return localizer.translate(TranslationString(string, *args, **kwargs))

    request.localizer = localizer
    request.translate = auto_translate
    request._ = auto_translate


def gettext(string, *args, **kwargs):
    return get_current_request().translate(string, *args, **kwargs)

def is_default_language():
    request = get_current_request()
    settings = get_current_registry().settings
    return request.locale_name == settings.get('pyramid.default_locale_name')
