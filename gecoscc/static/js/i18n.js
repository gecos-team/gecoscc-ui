/*jslint browser: true, vars: false */
/*global i18n_catalog, i18n_catalog_plural */

// Copyright (c) Django Software Foundation and individual contributors.
// All rights reserved.
//
// Redistribution and use in source and binary forms, with or without modification,
// are permitted provided that the following conditions are met:
//
//     1. Redistributions of source code must retain the above copyright notice,
//        this list of conditions and the following disclaimer.
//
//     2. Redistributions in binary form must reproduce the above copyright
//        notice, this list of conditions and the following disclaimer in the
//        documentation and/or other materials provided with the distribution.
//
//     3. Neither the name of Django nor the names of its contributors may be used
//        to endorse or promote products derived from this software without
//        specific prior written permission.
//
// THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
// ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
// WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
// DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
// ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
// (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
// LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND ON
// ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
// (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
// SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.


(function (catalog, plural) {
    "use strict";

    /* gettext library */

    window.simple_pluralidx = function (count) {
        return (count === 1) ? 0 : 1;
    };

    window.plural_pluralidx = function () {
        if (typeof plural === 'boolean') {
            return plural ? 1 : 0;
        }
        return plural;
    };
    window.gettext = function (msgid) {
        var value = catalog[msgid];
        if (value === undefined) {
            return msgid;
        }
        return (typeof value === 'string') ? value : value[0];
    };

    window.ngettext = function (singular, plural, count) {
        var value = catalog[singular];
        if (value === undefined) {
            return (count === 1) ? singular : plural;
        }
        if (plural) {
            return value[window.plural_pluralidx(count)];
        }
        return value[window.simple_pluralidx(count)];
    };

    window.gettext_noop = function (msgid) { return msgid; };

    window.pgettext = function (context, msgid) {
        var value = window.gettext(context + '\x04' + msgid);
        if (value.indexOf('\x04') !== -1) {
            value = msgid;
        }
        return value;
    };

    window.npgettext = function (context, singular, plural, count) {
        var value = window.ngettext(
            context + '\x04' + singular,
            context + '\x04' + plural,
            count
        );
        if (value.indexOf('\x04') !== -1) {
            value = window.ngettext(singular, plural, count);
        }
        return value;
    };

    window.interpolate = function (fmt, obj, named) {
        if (named) {
            return fmt.replace(/%\(\w+\)s/g, function (match) {
                return String(obj[match.slice(2, -2)]);
            });
        }
        return fmt.replace(/%s/g, function () {
            return String(obj.shift());
        });
    };

}(i18n_catalog, i18n_catalog_plural));
