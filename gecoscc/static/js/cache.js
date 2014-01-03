/*jslint browser: true, nomen: true */
/*global App, _ */

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

(function (App, _) {
    "use strict";

    var memory = {},
        makeRoom,
        cache;

    makeRoom = function () {
        var oldest = _.min(_.pairs(memory), function (el) {
            return el[1].timestamp;
        });
        return cache.drop(oldest[0]);
    };

    cache = {
        maxObjects: 50,

        set: function (key, obj) {
            var result;
            if (_.size(memory) >= this.maxObjects) {
                result = makeRoom();
            }

            memory[key] = {
                timestamp: Date.now(),
                object: obj
            };

            return result;
        },

        get: function (key) {
            if (this.has(key)) {
                return memory[key].object;
            }
        },

        has: function (key) {
            return _.has(memory, key);
        },

        drop: function (key) {
            var result = this.get(key);
            delete memory[key];
            return result;
        },

        reset: function () {
            memory = {};
        },

        size: function () {
            return _.size(memory);
        }
    };

    App.addInitializer(function () {
        App.instances.cache = cache;
    });
}(App, _));
