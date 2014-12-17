/*jslint browser: true, nomen: true */
/*global App, _ */

/*
* Copyright 2013, Junta de Andalucia
* http://www.juntadeandalucia.es/
*
* Authors:
*   Alejandro Blanco <alejandro.b.e@gmail.com>
*
* All rights reserved - EUPL License V 1.1
* https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
*/

(function (App, _) {
    "use strict";

    var createCache = function () {
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

        return cache;
    };

    App.createCache = createCache;
    App.instances.cache = createCache();
}(App, _));
