/*jslint browser: true, nomen: true, unparam: true */
/*global App, gettext */

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

App.module("Breadcrumb", function (Breadcrumb, App, Backbone, Marionette, $, _) {
    "use strict";

    Breadcrumb.Model = Backbone.Model.extend({
        defaults: {
            steps: [{
                url: "",
                text: gettext("Home")
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
        className: "breadcrumb bootstrap-admin-breadcrumb",

        events: {
            "click button": "navigateTo"
        },

        navigateTo: function (evt) {
            evt.preventDefault();
            App.instances.router.navigate($(evt.target).data("href"), {
                trigger: true
            });
        }
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
