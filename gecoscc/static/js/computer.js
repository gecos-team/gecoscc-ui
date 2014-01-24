/*jslint browser: true, nomen: true, unparam: true, vars: false */
/*global App, gettext, GecosUtils */

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


App.module("Computer.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.ComputerModel = App.GecosResourceModel.extend({
        resourceType: "computer",

        defaults: {
            type: "computer",
            lock: false,
            source: "gecos",
            name: "",
            identifier: "",
            ip: "",
            mac: "",
            family: "laptop",
            serial: "",
            registry: "",
            extra: ""
        }
    });
});

App.module("Computer.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.ComputerForm = App.GecosFormItemView.extend({
        template: "#computer-template",
        tagName: "div",
        className: "col-sm-12",

        groupsWidget: undefined,

        events: {
            "click #submit": "saveForm",
            "click #delete": "deleteModel",
            "change input": "validate"
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

        saveForm: function (evt) {
            evt.preventDefault();
            var $button = $(evt.target),
                promise;

            if (this.validate()) {
                $button.tooltip({
                    html: true,
                    title: "<span class='fa fa-spin fa-spinner'></span> " + gettext("Saving") + "..."
                });
                $button.tooltip("show");
                this.model.set({
                    memberof: this.groupsWidget.getChecked(),
                    name: this.$el.find("#name").val().trim(),
                    identifier: this.$el.find("#identifier").val().trim(),
                    ip: this.$el.find("#ip").val().trim(),
                    mac: this.$el.find("#mac").val().trim(),
                    family: this.$el.find("#family option:selected").val().trim(),
                    serial: this.$el.find("#serial").val().trim(),
                    registry: this.$el.find("#registry").val().trim(),
                    extra: this.$el.find("#extra").val().trim()
                });
                promise = this.model.save();
                promise.done(function () {
                    $button.tooltip("destroy");
                    $button.tooltip({
                        html: true,
                        title: "<span class='fa fa-check'></span> " + gettext("Done")
                    });
                    $button.tooltip("show");
                    setTimeout(function () {
                        $button.tooltip("destroy");
                    }, 2000);
                });
                promise.fail(function () {
                    $button.tooltip("destroy");
                    App.showAlert("error", gettext("Saving the Computer failed."),
                        gettext("Something went wrong, please try again in a few moments."));
                });
            } else {
                App.showAlert("error", gettext("Invalid data."),
                    gettext("Please, fix the errors in the fields below and try again."));
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
                        },
                        error: function () {
                            App.showAlert("error", gettext("Couldn't delete the Computer."),
                                gettext("Something went wrong, please try again in a few moments."));
                        }
                    });
                    GecosUtils.confirmModal.modal("hide");
                });
            GecosUtils.confirmModal.modal("show");
        }
    });
});
