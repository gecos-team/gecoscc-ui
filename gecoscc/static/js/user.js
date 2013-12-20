/*jslint browser: true, nomen: true, unparam: true */
/*global App, GecosUtils */

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

        ui: {
            memberof: "div#groups-widget"
        },

        events: {
            "click #submit": "saveForm",
            "click #delete": "deleteModel",
            "change input": "validate"
        },

        onRender: function () {
            var groups,
                widget,
                promise;

            if (App.instances.groups && App.instances.groups.length > 0) {
                groups = App.instances.groups;
                promise = $.Deferred();
                promise.resolve();
            } else {
                groups = new App.Group.Models.GroupCollection();
                promise = groups.fetch();
            }

            widget = new App.Group.Views.GroupWidget({
                el: this.ui.memberof[0],
                collection: groups,
                checked: this.model.get("memberof"),
                unique: false
            });
            promise.done(function () {
                widget.render();
            });
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

        deleteModel: function (evt) {
            evt.preventDefault();
            var that = this;

            GecosUtils.confirmModal.find("button.btn-danger")
                .off("click")
                .on("click", function (evt) {
                    that.model.destroy({
                        success: function () {
                            App.instances.tree.reloadTree();
                            App.instances.router.navigate("", { trigger: true });
                        }
                    });
                    GecosUtils.confirmModal.modal("hide");
                });
            GecosUtils.confirmModal.modal("show");
        }
    });
});
