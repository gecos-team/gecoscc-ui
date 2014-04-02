/*jslint browser: true, vars: false, nomen: true, unparam: true */
/*global App, jsonform, gettext */

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

App.module("Policies.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    /*
    * This view requires a policy model and a resource.
    *
    * Attributes:
    *   - model: The policy to configure
    *   - resource: The node of the tree subject of the policy
    */
    Views.PolicyGenericForm = Marionette.ItemView.extend({
        template: "#policy-template",
        tagName: "div",
        className: "col-sm-12",

        initialize: function (options) {
            if (!_.has(options, "resource")) {
                throw "This view requires a resource to be specified";
            }
            this.resource = options.resource;
        },

        serializeData: function () {
            var data = {
                    schema: this.model.get("schema")
                },
                id = this.model.get("id"),
                values;

            values = this.resource.get("policies")[id];
            if (!_.isUndefined(values)) {
                data.values = values;
            }
            return data;
        },

        render: function () {
            var data, policyData, template, $html;

            this.isClosed = false;

            this.triggerMethod("before:render", this);
            this.triggerMethod("item:before:render", this);

            policyData = this.mixinTemplateHelpers(this.model.toJSON());
            template = this.getTemplate();
            $html = $(Marionette.Renderer.render(template, policyData));

            data = this.serializeData();
            $html.find("form").jsonForm({
                // Object that describes the data model
                schema: data.schema,
                // Array that describes the layout of the form
                form: ["*"],
                // Callback function called upon form submission when values are valid
                onSubmitValid: _.bind(this.processForm, this)
            });

            this.$el.html($html);
            this.bindUIElements();

            this.triggerMethod("render", this);
            this.triggerMethod("item:rendered", this);

            return this;
        },

        events: {
            "click button#cancel": "onCancel",
            "click button#delete": "onDelete"
        },

        getResourceUrl: function () {
            var url = ["ou", _.last(this.resource.get("path").split(','))];
            url.push(this.resource.resourceType);
            url.push(this.resource.get("id"));
            return url.join('/');
        },

        processForm: function (values) {
            var id = this.model.get("id"),
                url = this.getResourceUrl();

            this.resource.get("policies")[id] = values;
            this.resource.save();
            App.showAlert(
                "success",
                gettext("Policy successfully saved."),
                gettext("Your changes are pending queuing in the staging area. In a few moments you'll be redirected to the resource.")
            );
            setTimeout(function () {
                App.instances.router.navigate(url, {
                    trigger: true
                });
            }, 2000);
        },

        onCancel: function (evt) {
            evt.preventDefault();
            App.instances.router.navigate(this.getResourceUrl(), {
                trigger: true
            });
        },

        onDelete: function (evt) {
            evt.preventDefault();
            var url = this.getResourceUrl();

            this.resource.removePolicy(this.model.get("id"));
            App.showAlert(
                "success",
                gettext("Policy successfully deleted."),
                gettext("Your changes are pending queuing in the staging area. In a few moments you'll be redirected to the resource.")
            );
            setTimeout(function () {
                App.instances.router.navigate(url, {
                    trigger: true
                });
            }, 2000);
        }
    });
});
