/*jslint browser: true, nomen: true, unparam: true, vars: false */
/*global App, gettext */

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

    Models.ComputerModel = App.Policies.Models.GecosResourceModel.extend({
        resourceType: "computer",

        defaults: {
            type: "computer",
            lock: false,
            source: "gecos",
            name: "",
            registry: "",
            family: "",
            users: "",
            uptime: "-",
            last_connection: new Date(),
            product_name: "",
            manufacturer: "-",
            cpu: "",
            ohai: "",
            ram: "",
            lsb: {},
            kernel: {},
            filesystem: {},
            policyCollection: new App.Policies.Models.PolicyCollection(),
            isEditable: undefined
        }
    });
});

App.module("Computer.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.ComputerForm = App.GecosFormItemView.extend({
        template: "#computer-template",
        tagName: "div",
        className: "col-sm-12",
        labelClass: "success",

        groupsWidget: undefined,
        policiesList: undefined,

        ui: {
            groups: "div#groups-widget",
            policies: "div#policies div.bootstrap-admin-panel-content"
        },

        events: {
            "click #submit": "saveForm",
            "click #delete": "deleteModel",
            "click #cut": "cutModel",
            "change input": "validate",
            "click button.refresh": "refresh"
        },

        onBeforeRender: function () {
            //Set domain dependent atributes
            var path = this.model.get("path");

            if (this.model.get("isEditable") !== undefined) { return; }

            if (path.split(',')[0] === "undefined") {
                this.model.set("isEditable", true);
            } else {
                this.getDomainAttrs();
            }

            this.checkLastConnection();
        },

        checkLastConnection: function () {
            var lastConnection = this.model.get("last_connection"),
                now = new Date(),
                interval;

            if(this.model.get("ohai") === "") {
                this.model.set("uptime", "-");
                this.model.set("last_connection", "Error");
                this.labelClass = "default";
                return;
            }

            interval = this.model.get("ohai").chef_client.interval;
            now.setMinutes(now.getMinutes() - interval);
            if (lastConnection < now) {
                this.model.set("uptime", "-");
                this.labelClass = "danger";
            }

            this.model.set("last_connection", this.calculateTimeToNow(lastConnection));
        },

        calculateTimeToNow: function (time) {
            var date_future = time,
                date_now = new Date(),
                seconds = Math.floor((date_now - date_future) / 1000),
                minutes = Math.floor(seconds / 60),
                hours = Math.floor(minutes / 60),
                days = Math.floor(hours / 24);

            hours = hours - (days * 24);
            minutes = minutes - (days * 24 * 60) - (hours * 60);
            seconds = seconds - (days * 24 * 60 * 60) - (hours * 60 * 60) - (minutes * 60);

            return [days, gettext("Days"), hours, gettext("Hours"), minutes, gettext("Minutes")].join(" ");
        },

        onRender: function () {
            if (!_.isUndefined(this.model.id)) {
                this.$el.find("#name").attr('disabled', 'disabled');
            }

            this.groupsWidget = new App.Group.Views.MultiGroupWidget({
                el: this.ui.groups[0],
                item_id: this.model.get("id"),
                ou_id: _.last(this.model.get("path").split(',')),
                checked: this.model.get("memberof"),
                disabled: !this.model.get("isEditable"),
                name: this.model.get("name")
            });
            this.groupsWidget.render();

            this.policiesList = new App.Policies.Views.PoliciesList({
                el: this.ui.policies[0],
                collection: this.model.get("policyCollection"),
                resource: this.model
            });

            this.policiesList.render();

            this.$el.find("#ohai-json").click(function (evt) {
                var $el = $(evt.target).find("span.fa");
                $el.toggleClass("fa-caret-right").toggleClass("fa-caret-down");
            });
            if (!this.model.get("isEditable")) {
                this.$el.find("textarea,input,select").prop("disabled", true);
            }
            this.$el.find(".connection-label").addClass("label-" + this.labelClass);
        },

        saveForm: function (evt) {
            evt.preventDefault();
            this.saveModel($(evt.target), {
                memberof: _.bind(this.groupsWidget.getChecked, this.groupsWidget),
                name: "#name",
                family: "#family option:selected",
                registry: "#registry"
            });
        }
    });
});
