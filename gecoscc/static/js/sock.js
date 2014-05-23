/*jslint browser: true, nomen: true, unparam: true, vars: false */

// Copyright 2014 Junta de Andalucia
//
// Licensed under the EUPL, Version 1.1 or - as soon they
// will be approved by the European Commission - subsequent
// versions of the EUPL (the "Licence");
// You may not use this work except in compliance with the
// Licence.
// You may obtain a copy of the Licence at:
//
// http://ec.europa.eu/idabc/eupl
//
// Unless required by applicable law or agreed to in
// writing, software distributed under the Licence is
// distributed on an "AS IS" basis,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
// express or implied.
// See the Licence for the specific language governing
// permissions and limitations under the Licence.

var MessageManager = function() {
    var Sock = new SockJS('http://localhost:6543/sockjs');
    var manager_handlers = {};

    Sock.onopen = function() {
    };

    Sock.onmessage = function(e) {
        var result = jQuery.parseJSON(e.data);
        if (result.hasOwnProperty('action')) {
            var handlers = manager_handlers[result.action] || [];
            for (var i=0, handler; handler=handlers[i]; ++i) {
                handler(result.object);
            }
        }
    };

    Sock.onclose = function() {
    };

    return {
        bind: function(action, callback) {
            var handlers = manager_handlers[action] = manager_handlers[action] || [];
            handlers.push(callback);
            return this;
        }
    }
};
