/*jslint browser: true, nomen: true, unparam: true, vars: false */
/*global io, jQuery */

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

var MessageManager = function () {
    "use strict";
    var socket = io.connect(),
        manager_handlers = {};
    socket.emit('subscribe');

    socket.on("message", function (result) {
        var handlers,
            handler,
            i;

        if (result.hasOwnProperty('redis')) {
            if(result.redis === 'error'){
                $("#redis-modal").modal({backdrop: 'static'});
            }
        }
        if (result.hasOwnProperty('action')) {
            handlers = manager_handlers[result.action] || [];
            for (i = 0; i < handlers.length; i += 1) {
                handler = handlers[i];
                handler(result);
            }
        }
    });

    socket.on('disconnect', function() {
        $("#socket-modal").modal({backdrop: 'static'});
    });

    return {
        bind: function (action, callback) {
            var handlers = manager_handlers[action] = manager_handlers[action] || [];
            handlers.push(callback);
            return this;
        },
        socket: socket
    };
};
