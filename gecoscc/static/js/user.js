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

App.module("User.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.UserModel = Backbone.Model.extend({
        defaults: {
            type: "user",
            lock: false,
            source: "gecos",
            first_name: "",
            last_name: "",
            name: "",
            address: "",
            phone: "",
            email: ""
        },

        url: function () {
            var url = "/api/users/";
            if (this.has("id")) {
                url += this.get("id") + '/';
            }
            return url;
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
                    App.instances.router.navigate("ou/" + parent.model.id + "/user/" + resp._id, {
                        trigger: true
                    });
                });
            }

            return promise;
        }
    });
});

App.module("User.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.UserForm = App.GecosFormItemView.extend({
        template: "#user-template",
        tagName: "div",
        className: "col-sm-12",

        events: {
            "click #submit": "saveForm",
            "change input": "validate",

            "keyup #permission-filter": "permissionFilter",
            "click #permission-filter-btn": "permissionFilter"
        },

        saveForm: function (evt) {
            evt.preventDefault();
            var $button = $(evt.target),
                promise;

            if (this.validate()) {
                $button.tooltip({
                    html: true,
                    title: "<span class='fa fa-spin fa-spinner'></span> Guardando..." // TODO translate
                });
                $button.tooltip("show");
                this.model.set({
                    name: this.$el.find("#username").val().trim(),
                    phone: this.$el.find("#phone").val().trim(),
                    email: this.$el.find("#email").val().trim(),
                    first_name: this.$el.find("#firstname").val().trim(),
                    last_name: this.$el.find("#lastname").val().trim(),
                    address: this.$el.find("#address").val().trim()
                });
                // TODO password
                // TODO permissions
                promise = this.model.save();
                promise.done(function () {
                    $button.tooltip("destroy");
                    $button.tooltip({
                        html: true,
                        title: "<span class='fa fa-check'></span> Terminado" // TODO translate
                    });
                    $button.tooltip("show");
                    setTimeout(function () {
                        $button.tooltip("destroy");
                    }, 2000);
                });
            }
        },

        permissionFilter: function (evt) {
            var filter = $(evt.target);
            if (filter.is("input")) {
                filter = filter.val();
            } else {
                filter = filter.parents('div.input-group').find("input").val();
            }
            $("label.permission").each(function (index, label) {
                var $label = $(label),
                    filterReady = filter.trim().toLowerCase(),
                    text = $label.text().trim().toLowerCase();
                if (filterReady.length === 0 || text.indexOf(filterReady) >= 0) {
                    $label.parent().show();
                } else {
                    $label.parent().hide();
                }
            });
        }
    });
});
