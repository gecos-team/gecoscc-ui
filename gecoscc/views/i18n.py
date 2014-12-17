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

import os

import gettext as gettext_module
import simplejson as json
import six

import gecoscc

from pyramid.threadlocal import get_current_registry
from pyramid.view import view_config


@view_config(route_name='i18n_catalog', renderer='templates/i18n.jinja2')
def i18n_catalog(context, request):
    current_language = locale_language = request._LOCALE_
    plural = None
    catalog = {}
    catalog_js = 'gecoscc_js'
    locale_path = os.path.join(os.sep.join(gecoscc.__file__.split(os.sep)[:-1]), 'locale')
    if not gettext_module.find(catalog_js, locale_path, [current_language]):
        settings = get_current_registry().settings
        locale_language = settings['pyramid.default_locale_name']
    # Inspirated by https://github.com/django/django/blob/master/django/views/i18n.py#L192
    t = gettext_module.translation(catalog_js, locale_path, [locale_language])._catalog
    if '' in t:
        for l in t[''].split('\n'):
            if l.startswith('Plural-Forms:'):
                plural = l.split(':', 1)[1].strip()
    if plural is not None:
        # this should actually be a compiled function of a typical plural-form:
        # Plural-Forms: nplurals=3; plural=n%10==1 && n%100!=11 ? 0 : n%10>=2 && n%10<=4 && (n%100<10 || n%100>=20) ? 1 : 2;
        plural = [el.strip() for el in plural.split(';') if el.strip().startswith('plural=')][0].split('=', 1)[1]

    pdict = {}
    maxcnts = {}
    for k, v in t.items():
        if k == '':
            continue
        if isinstance(k, six.string_types):
            catalog[k] = v
        elif isinstance(k, tuple):
            msgid = k[0]
            cnt = k[1]
            maxcnts[msgid] = max(cnt, maxcnts.get(msgid, 0))
            pdict.setdefault(msgid, {})[cnt] = v
        else:
            raise TypeError(k)
    for k, v in pdict.items():
        catalog[k] = [v.get(i, '') for i in range(maxcnts[msgid] + 1)]

    return {'catalog': json.dumps(catalog),
            'plural': json.dumps(plural)}
