/*jslint browser: true, vars: false, nomen: true, unparam: true */
/*global App, jsonform, gettext, jjv */

/*
* Copyright 2013, Junta de Andalucia
* http://www.juntadeandalucia.es/
*
* Authors:
*   Alberto Beiztegui <albertobeiz@gmail.com>
*   Alejandro Blanco <alejandro.b.e@gmail.com>
*
* All rights reserved - EUPL License V 1.1
* https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
*/

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
            var that = this;
            if (!_.has(options, "resource")) {
                throw "This view requires a resource to be specified";
            }
            this.resource = options.resource;
            this.disabled = _.some(this.resource.get("master_policies"), function (a, k) { return k === that.model.get("id"); });
        },

        serializeData: function () {
            var data = {
                    schema: this.model.get("schema")
                },
                id = this.model.get("id");

            data.values = this.resource.get("policies")[id] || {};
            data.disabled = this.disabled;
            return data;
        },

        render: function () {
            var data, policyData, template, $html, options, formLayout;

            this.isClosed = false;

            this.triggerMethod("before:render", this);
            this.triggerMethod("item:before:render", this);

            policyData = this.mixinTemplateHelpers(this.model.toJSON());
            policyData.resource = this.resource;
            policyData.name = policyData["name_" + App.language] || policyData.name;

            if (this.model.get('slug').slice(-4) === '_res') {
                policyData.slug = this.model.get('slug').slice(0, -4);
            }
            formLayout = _.isEmpty(this.model.get('form')) ? "*" : this.model.get('form');
            //console.log("formLayout: " + formLayout);

            template = this.getTemplate();
            $html = $(Marionette.Renderer.render(template, policyData));

            data = this.serializeData();
            options = {
                // Object that describes the data model
                schema: data.schema,
                // Array that describes the layout of the form
                form: [formLayout],
                // Callback function called upon form submission when values are valid
                onSubmitValid: _.bind(this.processForm, this)
            };
            if (_.has(data, "values")) { options.value = data.values; }
            options.validate = jjv();
            options.resourceId = this.resource.get("id");
            options.ouId = _.last(this.resource.get("path").split(","));
            options.slug = policyData.slug;
            options.customFormItems = data.schema['customFormItems'];
            $html.find("form").jsonForm(options);
            
            if ("debug_mode" == policyData.slug) {
                // Set expire date time on debug_mode policy
                var input = $html.find("form").find("input[name='expire_datetime']");
                
                var expiredate = new Date(); 
                expiredate.setSeconds(expiredate.getSeconds() + 
                    App.debug_mode_timeout);
                    
                var datetime = expiredate.toGMTString();
                input.val(datetime);
                
                // Hide real input field with the GMT date and time
                input.css("display", "none");
                
                // Show the local date time
                var local_datetime = expiredate.toLocaleDateString(App.language) + 
                    " "+ expiredate.toLocaleTimeString(App.language);
                input.after('<div style="padding-top: 7px;">'+local_datetime+'</div>');
                                
                
            }

            this.$el.html($html);
            this.bindUIElements();

            this.triggerMethod("render", this);
            this.triggerMethod("item:rendered", this);

            return this;
        },

        onBeforeRender: function () {
            var autoreverse = this.model.get('autoreverse');

            if (autoreverse) {
                this.alertWarning(
                    gettext("This is an auto-reverting policy."),
                    "<br/> - " + gettext("Any configuration element removed from the form will be inmediatly removed from the corresponding workstations.")
                );
            }
        },

        alertWarning: function (strong, text) {
            this.model.set("iconClass", "info-icon-warning");
            this.model.set("labelClass", "label-warning");
            App.showAlert(
                "warning",
                strong,
                text
            );
        },

        onRender: function () {
            if (this.disabled) {
                this.$el.find("textarea,input,select").prop("disabled", true);
                this.$el.find(".btn-xs").addClass("disabled");
            }
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
            var url = this.getResourceUrl();

            this.resource.addPolicy(this.model, values);

            App.instances.router.navigate(url, {
                trigger: true
            });
            $("#policy-tab a").tab("show");
    
            App.showAlert(
                "success",
                gettext("Policy successfully saved.")
            );
        },

        onCancel: function (evt) {
            evt.preventDefault();
            App.instances.router.navigate(this.getResourceUrl(), {
                trigger: true
            });
            $("#policy-tab a").tab("show");
        },

        onDelete: function (evt) {
            evt.preventDefault();
            var url = this.getResourceUrl();

            this.resource.removePolicy(this.model.get("id"));

            App.instances.router.navigate(url, {
                trigger: true
            });
            $("#policy-tab a").tab("show");

            App.showAlert(
                "success",
                gettext("Policy successfully deleted.")
            );
        }
    });
});
