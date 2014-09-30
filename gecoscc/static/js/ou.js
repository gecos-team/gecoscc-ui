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

    Models.OUModel = App.Policies.Models.GecosResourceModel.extend({
        resourceType: "ou",
        defaults: {
            type: "ou",
            source: "gecos",
            lock: false,
            extra: "",
            policyCollection: new App.Policies.Models.PolicyCollection(),
            master: "gecos",
            master_policies: {},
            isDomain: function () {
                return this.path.split(',').length === 2;
            },
            isEditable: undefined
        }
    });
});

App.module("OU.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.OUForm = App.GecosFormItemView.extend({
        template: "#ou-template",
        tagName: "div",
        className: "col-sm-12",

        ui: {
            policies: "div#policies div.bootstrap-admin-panel-content"
        },
        events: {
            "click #submit": "saveForm",
            "click #delete": "deleteModel",
            "change input": "validate",
            "click button.refresh": "refresh"
        },

        policiesList: undefined,

        onBeforeRender: function () {
            var path = this.model.get("path"),
                domain,
                that;

            if (this.model.get("isEditable") !== undefined) { return; }
            domain = path.split(',')[2];
            if (path === "root") {
                this.model.set("isEditable", true);
            } else if (path.split(',').length === 2) {
                this.model.set("isEditable", this.model.get("master") === "gecos");
            } else {
                this.getDomainAttrs();
            }
        },

        onRender: function () {
            if (!_.isUndefined(this.model.id)) {
                this.$el.find("#name").attr('disabled', 'disabled');
            }
            this.policiesList = new App.Policies.Views.PoliciesList({
                el: this.ui.policies[0],
                collection: this.model.get("policyCollection"),
                resource: this.model
            });
            this.policiesList.render();
        },

        saveForm: function (evt) {
            evt.preventDefault();
            this.saveModel($(evt.target), {
                name: "#name",
                extra: "#extra"
            });
        }
    });
});
