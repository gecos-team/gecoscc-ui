/*jslint browser: true, vars: false, nomen: true */
/*global App, Backbone, jQuery, _ */

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

(function (App, Backbone, $, _) {
    "use strict";

    var NewElementView,
        LoaderView,
        AlertView,
        numericRegex,
        emailRegex,
        ipRegex,
        urlRegex,
        applyRegex;

    /*
    * Regular expressions taken from:
    *
    * validate.js 1.3
    * Copyright (c) 2011 Rick Harrison, http://rickharrison.me
    * validate.js is open sourced under the MIT license.
    * Portions of validate.js are inspired by CodeIgniter.
    * http://rickharrison.github.com/validate.js
    */

    numericRegex = /^[0-9]+$/;
//     integerRegex = /^\-?[0-9]+$/;
//     decimalRegex = /^\-?[0-9]*\.?[0-9]+$/;
    emailRegex = /^[a-zA-Z0-9.!#$%&amp;'*+\-\/=?\^_`{|}~\-]+@[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*$/;
//         alphaRegex = /^[a-z]+$/i,
//         alphaNumericRegex = /^[a-z0-9]+$/i,
//         alphaDashRegex = /^[a-z0-9_\-]+$/i,
//         naturalRegex = /^[0-9]+$/i,
//         naturalNoZeroRegex = /^[1-9][0-9]*$/i,
    ipRegex = /^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[0-9]{1,2})\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[0-9]{1,2})$/;
//         base64Regex = /[^a-zA-Z0-9\/\+=]/i,
//         numericDashRegex = /^[\d\-\s]+$/,
    urlRegex = /^((http|https):\/\/(\w+:{0,1}\w*@)?(\S+)|)(:[0-9]+)?(\/|\/([\w#!:.?+=&%@!\-\/]))?$/;

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

    // Custom models and views, for reusing code between resources

    App.GecosResourceModel = Backbone.Model.extend({
        url: function () {
            var url = "/api/" + this.resourceType + "s/";
            if (this.has("id")) {
                url += this.get("id") + '/';
            }
            return url;
        },

        parse: function (response) {
            var result = _.clone(response);
            result.id = response._id;
            return result;
        },

        save: function (key, val, options) {
            var isNew = this.isNew(),
                promise = Backbone.Model.prototype.save.call(this, key, val, options);

            if (isNew) {
                promise.done(function (resp) {
                    var tree = App.instances.tree.get("tree"),
                        parentId = _.last(resp.path.split(',')),
                        parent = tree.first(function (n) {
                            return n.model.id === parentId;
                        });

                    while (parent.children.length > 0) {
                        parent.children[0].drop();
                    }
                    App.instances.tree.loadFromNode(parent);
                    App.instances.router.navigate("ou/" + parent.model.id + '/' + this.resourceType + '/' + resp._id, {
                        trigger: true
                    });
                });
            }

            return promise;
        }
    });

    App.GecosFormItemView = Backbone.Marionette.ItemView.extend({
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
                } else if ($el.val().trim() === "") {
                    // Not required and empty, avoid more validation
                    return;
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

    NewElementView = Backbone.Marionette.ItemView.extend({
        template: "#new-element-template",

        serializeData: function () {
            // This view needs no model
            return {
                ouID: this.containerId
            };
        }
    });

    App.instances.newElementView = new NewElementView();

    LoaderView = Backbone.Marionette.ItemView.extend({
        template: "#loader-template",

        serializeData: function () {
            return {}; // This view needs no model
        }
    });

    App.instances.loaderView = new LoaderView();

    AlertView = Backbone.Marionette.ItemView.extend({
        template: "#alert-template",
        tagName: "div",
        className: "col-sm-12",

        data: {
            cssClass: "info",
            strongText: "",
            regularText: ""
        },

        serializeData: function () {
            return this.data;
        },

        initialize: function (options) {
            if (_.has(options, "type")) {
                this.data.cssClass = options.type;
            }
            if (_.has(options, "bold")) {
                this.data.strongText = options.bold;
            }
            if (_.has(options, "text")) {
                this.data.regularText = options.text;
            }
        },

        onRender: function () {
            var $el = this.$el;
            $('html, body').animate({
                scrollTop: $el.offset().top
            }, 1000);
        }
    });

    App.showAlert = function (type, bold, text) {
        var view;

        if (type === "error") { type = "danger"; }
        view = new AlertView({
            type: type,
            bold: bold,
            text: text
        });
        App.alerts.show(view);
    };
}(App, Backbone, jQuery, _));
