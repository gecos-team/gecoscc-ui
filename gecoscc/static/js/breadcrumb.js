/*jslint browser: true, nomen: true, unparam: true */
/*global App */

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

App.module("Breadcrumb", function (Breadcrumb, App, Backbone, Marionette, $, _) {
    "use strict";

    Breadcrumb.Model = Backbone.Model.extend({
        defaults: {
            steps: [{
                url: '/',
                text: 'Inicio' // TODO translate
            }]
        },

        addStep: function (url, text) {
            this.get("steps").push({
                url: url,
                text: text
            });
            this.trigger("change"); // This is necessary because pushing an
            // object into an array doesn't change its reference, and the model
            // doesn't notice anything
        },

        setSteps: function (steps) {
            var first = _.first(this.get("steps")),
                newsteps = _.union([first], steps);
            this.set("steps", newsteps);
        }
    });

    Breadcrumb.View = Marionette.ItemView.extend({
        template: "#breadcrumb-template",
        tagName: "ol",
        className: "breadcrumb bootstrap-admin-breadcrumb"
    });

    App.addInitializer(function () {
        var view;
        App.instances.breadcrumb = new Breadcrumb.Model();
        view = new Breadcrumb.View({
            model: App.instances.breadcrumb
        });
        App.instances.breadcrumb.on("change", function () {
            App.breadcrumb.show(view);
        });
        App.instances.breadcrumb.trigger("change");
    });
});
