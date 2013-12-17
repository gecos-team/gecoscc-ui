/*jslint browser: true, vars: false */
/*global App:true, Backbone */

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

var App;

(function (Backbone) {
    "use strict";
    var Router,
        Loader;

    App = new Backbone.Marionette.Application();

    // To store references to root instances
    App.instances = {};

    App.addRegions({
        // main
        main: "#viewport-main"
    });

    Loader = Backbone.Marionette.ItemView.extend({
        render: function () {
            this.$el.html('<p style="font-size: 3em;">' +
                '<span class="fa fa-spin fa-spinner"></span> Loading...</p>');
            return this;
        }
    });

    App.instances.loader = new Loader();

    Router = Backbone.Marionette.AppRouter.extend({
        appRoutes: {
            "": "loadTable"
//             "ou/:containerid/user": "newUser",
//             "ou/:containerid/user/:userid": "loadUser",
//             "ou/:containerid/ou": "newOU",
//             "ou/:containerid/ou/:ouid": "loadOU"
        },

        controller: {
            loadTable: function () {
                var view;
                App.main.show(App.instances.loader);

                if (!App.instances.groups) {
                    App.instances.groups = new App.Group.Models.GroupCollection();
                }
                App.instances.groups
                    .off("change")
                    .on("change", function () {
                        App.main.show(view);
                    });

                view = new App.Group.Views.GroupTable({
                    collection: App.instances.groups
                });
                App.instances.groups.fetch({
                    success: function () {
                        App.instances.groups.trigger("change");
                    }
                });
            }
        }
    });

    App.instances.router = new Router();

    App.on('initialize:after', function () {
        if (Backbone.history) {
            Backbone.history.start();
        }
        App.instances.router.controller.loadTable();
    });
}(Backbone));
