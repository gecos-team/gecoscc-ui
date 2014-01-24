/*jslint browser: true, nomen: true, unparam: true */
/*global App, GecosUtils, gettext */

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

    Models.UserModel = App.GecosResourceModel.extend({
        resourceType: "user",

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
        }
    });
});

App.module("User.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.UserForm = App.GecosFormItemView.extend({
        template: "#user-template",
        tagName: "div",
        className: "col-sm-12",

        groupsWidget: undefined,

        ui: {
            passwd1: "input#passwd1",
            passwd2: "input#passwd2"
        },

        events: {
            "click #submit": "saveForm",
            "click #delete": "deleteModel",
            "change input": "validate",
            "keyup input:password": "checkPasswords"
        },

        onRender: function () {
            var groups,
                promise;

            if (App.instances.groups && App.instances.groups.length > 0) {
                groups = App.instances.groups;
                promise = $.Deferred();
                promise.resolve();
            } else {
                groups = new App.Group.Models.GroupCollection();
                promise = groups.fetch({
                    success: function () {
                        App.instances.groups = groups;
                    }
                });
            }

            this.groupsWidget = new App.Group.Views.GroupWidget({
                el: this.$el.find("div#groups-widget")[0],
                collection: groups,
                checked: this.model.get("memberof"),
                unique: false
            });
            promise.done(_.bind(function () {
                this.groupsWidget.render();
            }, this));
        },

        customValidate: function () {
            return this.checkPasswords();
        },

        saveForm: function (evt) {
            evt.preventDefault();
            this.saveModel($(evt.target), {
                memberof: _.bind(this.groupsWidget.getChecked, this),
                name: "#username",
                phone: "#phone",
                email: "#email",
                first_name: "#firstname",
                last_name: "#lastname",
                address: "#address",
                password: "#passwd1"
            });
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
                        },
                        error: function () {
                            App.showAlert("error", gettext("Couldn't delete the User."),
                                gettext("Something went wrong, please try again in a few moments."));
                        }
                    });
                    GecosUtils.confirmModal.modal("hide");
                });
            GecosUtils.confirmModal.modal("show");
        },

        checkPasswords: function () {
            var result = false,
                p1 = this.ui.passwd1.val(),
                p2 = this.ui.passwd2.val();

            if (p1 === p2) {
                result = true;
                this.ui.passwd1.parents(".form-group").first().removeClass("has-error");
                this.ui.passwd2.parents(".form-group").first().removeClass("has-error");
            } else {
                this.ui.passwd1.parents(".form-group").first().addClass("has-error");
                this.ui.passwd2.parents(".form-group").first().addClass("has-error");
            }

            return result;
        }
    });
});
