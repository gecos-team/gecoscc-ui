/*jslint browser: true */
/*global App: true, Backbone */

// Copyright 2013 Junta de Andalucia
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

// This file creates the global App variable, it should be loaded as soon as
// possible
var App;

(function (Backbone) {
    "use strict";

    App = new Backbone.Marionette.Application();

    // To store references to models root instances
    App.instances = {};

    App.addRegions({
        // sidebar
        tree: "#ex-tree",
        events: "#events",
        // main
        main: "#viewport-main"
    });

    var Router = Backbone.Marionette.AppRouter.extend({
        appRoutes: {
            "user/:id": "loadUser"
        },

        controller: {
            loadUser: function (id) {
                var model = new App.User.Models.UserModel({ id: id }),
                    view = new App.User.Views.UserForm({ model: model });
                // model.fetch(); TODO
                App.main.show(view);
            }
        }
    });

    App.instances.router = new Router();

    App.on('initialize:after', function () {
        if (Backbone.history) {
            Backbone.history.start();
        }
    });
}(Backbone));
