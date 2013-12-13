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

App.module("OU.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.OUModel = Backbone.Model.extend({
        defaults: {
            type: "ou",
            source: "gecos",
            lock: false,
            policies: [],
            policiesCollection: null
        },

        url: function () {
            var url = "/api/ous/";
            if (this.has("id")) {
                url += this.get("id") + '/';
            }
            return url;
        },

        parse: function (response) {
            var result = _.clone(response);
            result.policiesCollection = new Models.PolicyCollection(response.policies);
            return result;
        },

        save: function (key, val, options) {
            var tempId, promise;

            // Remove temporal ID
            if (this.has("id") && this.get("id").indexOf("NEWNODE") === 0) {
                tempId = this.get("id");
                this.unset("id", { silent: true });
            }

            promise = Backbone.Model.prototype.save.call(this, key, val, options);

            if (tempId) {
                promise.done(function (resp) {
                    var tree = App.instances.tree.get("tree"),
                        node = tree.first(function (n) {
                            return n.model.id === tempId;
                        }),
                        parent = node.parent;

                    while (parent.children.length > 0) {
                        parent.children[0].drop();
                    }
                    App.instances.tree.loadFromNode(parent);
                    App.instances.router.navigate("ou/" + parent.model.id + "/ou/" + resp._id, {
                        trigger: true
                    });
                });
            }

            return promise;
        }
    });

    Models.PolicyModel = Backbone.Model.extend({});

    Models.PolicyCollection = Backbone.Collection.extend({
        model: Models.PolicyModel
    });
});

App.module("OU.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.OUForm = App.GecosFormItemView.extend({
        template: "#ou-template",
        tagName: "div",
        className: "col-sm-12",

        events: {
            "click #submit": "saveForm",
            "change input": "validate"
        },

        saveForm: function (evt) {
            evt.preventDefault();
            var $button = $(evt.target),
                promise;

            if (this.validate()) {
                $button.tooltip({
                    html: true,
                    title: "<span class='fa fa-spin fa-spinner'></span> Saving..." // TODO translate
                });
                $button.tooltip("show");
                this.model.set({
                    name: this.$el.find("#name").val().trim(),
                    extra: this.$el.find("#extra").val().trim()
                });
                promise = this.model.save();
                promise.done(function () {
                    $button.tooltip("destroy");
                    $button.tooltip({
                        html: true,
                        title: "<span class='fa fa-check'></span> Done" // TODO translate
                    });
                    $button.tooltip("show");
                    setTimeout(function () {
                        $button.tooltip("destroy");
                    }, 2000);
                });
            }
        }
    });
});
