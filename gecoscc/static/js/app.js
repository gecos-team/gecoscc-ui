/*jslint browser: true, nomen: true */
/*global App: true, Backbone, jQuery, _ */

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

(function (Backbone, $, _) {
    "use strict";

    App = new Backbone.Marionette.Application();

    // To store references to models root instances
    App.instances = {};

    App.addRegions({
        // sidebar
        tree: "#ex-tree",
        events: "#events",
        // breadcrumb
        breadcrumb: "#breadcrumb",
        // main
        main: "#viewport-main"
    });

    var Router = Backbone.Marionette.AppRouter.extend({
        appRoutes: {
            "user/:id": "loadUser"
        },

        controller: {
            loadUser: function (id) {
                var model = new App.User.Models.UserModel(),
                    view = new App.User.Views.UserForm({ model: model });
                App.instances.breadcrumb.setSteps([{
                    url: "#user/" + id,
                    text: "Usuario" // translation
                }]);
                App.main.show(view); // Render the loader indicator
                model.set("id", id); // Add an ID after rendering the loader
                model.on("change", function () {
                    App.main.show(view);
                });
                model.fetch();
            }
        }
    });

    App.instances.router = new Router();

    /*
    * Regular expressions taken from:
    *
    * validate.js 1.3
    * Copyright (c) 2011 Rick Harrison, http://rickharrison.me
    * validate.js is open sourced under the MIT license.
    * Portions of validate.js are inspired by CodeIgniter.
    * http://rickharrison.github.com/validate.js
    */

    var numericRegex = /^[0-9]+$/,
//         integerRegex = /^\-?[0-9]+$/,
//         decimalRegex = /^\-?[0-9]*\.?[0-9]+$/,
        emailRegex = /^[a-zA-Z0-9.!#$%&amp;'*+\-\/=?\^_`{|}~\-]+@[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*$/,
//         alphaRegex = /^[a-z]+$/i,
//         alphaNumericRegex = /^[a-z0-9]+$/i,
//         alphaDashRegex = /^[a-z0-9_\-]+$/i,
//         naturalRegex = /^[0-9]+$/i,
//         naturalNoZeroRegex = /^[1-9][0-9]*$/i,
        ipRegex = /^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[0-9]{1,2})\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[0-9]{1,2})$/i,
//         base64Regex = /[^a-zA-Z0-9\/\+=]/i,
//         numericDashRegex = /^[\d\-\s]+$/,
        urlRegex = /^((http|https):\/\/(\w+:{0,1}\w*@)?(\S+)|)(:[0-9]+)?(\/|\/([\w#!:.?+=&%@!\-\/]))?$/,

    /*
    * End - validate.js
    */

        applyRegex = function (regex, $el) {
            var valid = true;
            if (regex.test($el.val().trim())) {
                $el.parent().removeClass("has-error");
            } else {
                $el.parent().addClass("has-error");
                valid = false;
            }
            return valid;
        };

    App.GecosFormItemView = Backbone.Marionette.ItemView.extend({
        render: function () {
            if (this.model.isNew()) {
                this.$el.html("<p style='font-size: 3em;'><span class='fa " +
                    "fa-spinner fa-spin'></span> Loading...</p>");
            } else {
                Backbone.Marionette.ItemView.prototype.render.call(this);
            }
            return this;
        },

        validate: function (evt) {
            var valid = true,
                $elems;

            if (evt) {
                $elems = [evt.target];
            } else {
                $elems = this.$el.find("input");
            }

            _.each($elems, function (el) {
                var $el = $(el);

                if ($el.is("[required]")) {
                    if ($el.val().trim() === "") {
                        $el.parent().addClass("has-error");
                        valid = false;
                    } else {
                        $el.parent().removeClass("has-error");
                    }
                }

                if ($el.is("[type=email]")) {
                    valid = valid && applyRegex(emailRegex, $el);
                } else if ($el.is("[type=number]")) {
                    valid = valid && applyRegex(numericRegex, $el);
                } else if ($el.is("[type=url]")) {
                    valid = valid && applyRegex(urlRegex, $el);
                } else if ($el.is("[type=tel]")) {
                    valid = valid && applyRegex(numericRegex, $el);
                } else if ($el.is(".ip")) {
                    valid = valid && applyRegex(ipRegex, $el);
                }
            });

            return valid;
        }
    });

    App.on('initialize:after', function () {
        if (Backbone.history) {
            Backbone.history.start();
        }
    });
}(Backbone, jQuery, _));
