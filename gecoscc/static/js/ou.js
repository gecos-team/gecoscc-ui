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
