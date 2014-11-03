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
            product_name: "",
            manufacturer: "-",
            cpu: "",
            ohai: "",
            ram: "",
            lsb: {},
            kernel: {},
            filesystem: {},
            policyCollection: new App.Policies.Models.PolicyCollection(),
            isEditable: undefined,
            icon: "desktop",
            iconClass: "info-icon-success",
            error_last_saved: false
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
            var now = new Date(),
                lastConnection,
                interval,
                errors = [];

            //No data received
            if (this.model.get("ohai") === "" || _.isUndefined(this.model.get("ohai").ohai_time)) {
                this.model.set("uptime", "-");
                this.model.set("last_connection", "Error");
                this.model.set("iconClass", "info-icon-danger");
                this.labelClass = "danger";
                App.showAlert(
                    "error",
                    gettext("No data has been received from this workstation."),
                    gettext("Check connection with Chef server.")
                );
                return;
            }

            lastConnection = new Date(this.model.get("ohai").ohai_time * 1000);
            interval = this.model.get("ohai").chef_client.interval / 60;
            now.setMinutes(now.getMinutes() - interval);

            if (lastConnection < now) {
                this.model.set("uptime", "-");
                this.model.set("iconClass", "info-icon-danger");
                this.labelClass = "danger";
                errors.push("<br/> - " + gettext("Chef client is not being executed on time."));
            }

            if (this.model.get("error_last_saved")) {
                this.model.set("iconClass", "info-icon-danger");
                errors.push("<br/> - " + gettext("Last chef client had problems during its execution."));
            }

            if (!_.isEmpty(errors)) {
                App.showAlert(
                    "error",
                    gettext("This workstation is not working properly:"),
                    errors
                );
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
