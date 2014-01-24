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

App.module("OU.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.OUModel = App.GecosResourceModel.extend({
        resourceType: "ou",

        defaults: {
            type: "ou",
            source: "gecos",
            lock: false,
            policies: [],
            policiesCollection: null
        },

        parse: function (response) {
            var result = _.clone(response);
            result.policiesCollection = new Models.PolicyCollection(response.policies);
            result.id = response._id;
            return result;
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
            "click #delete": "deleteModel",
            "change input": "validate"
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
                    name: this.$el.find("#name").val().trim(),
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
                    App.showAlert("error", gettext("Saving the OU failed."),
                        gettext("Something went wrong, please try again in a few moments."));
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
                        },
                        error: function () {
                            App.showAlert("error", gettext("Couldn't delete the OU."),
                                gettext("Something went wrong, please try again in a few moments."));
                        }
                    });
                    GecosUtils.confirmModal.modal("hide");
                });
            GecosUtils.confirmModal.modal("show");
        }
    });
});
