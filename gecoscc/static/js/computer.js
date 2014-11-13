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
            labelClass: "label-success",
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

            this.checkErrors();
        },

        checkErrors: function () {
            var now = new Date(),
                lastConnection,
                interval,
                chef_client;

            //No data received
            if (this.model.get("ohai") === "" || _.isUndefined(this.model.get("ohai").ohai_time)) {
                this.alertError(
                    gettext("No data has been received from this workstation."),
                    gettext("Check connection with Chef server.")
                );
                return;
            }

            lastConnection = new Date(this.model.get("ohai").ohai_time * 1000);
            chef_client = this.model.get("ohai").chef_client;
            if (_.isUndefined(chef_client)) {
                this.alertError(gettext("This workstation has incomplete Ohai information."));
                return;
            }

            interval = this.model.get("ohai").chef_client.interval / 60;
            now.setMinutes(now.getMinutes() - interval);
            if (lastConnection < now) {
                this.model.set("uptime", "-");
                this.model.set("iconClass", "info-icon-warning");
                this.model.set("labelClass", "label-warning");
                App.showAlert(
                    "warning",
                    gettext("This workstation is not working properly:"),
                    "<br/> - " + gettext("Chef client is not being executed on time.")
                );
            }

            if (this.model.get("error_last_saved")) {
                this.model.set("iconClass", "info-icon-danger");
                App.showAlert(
                    "error",
                    gettext("This workstation is not working properly:"),
                    "<br/> - " + gettext("Last chef client had problems during its execution.")
                );
            }

            this.model.set("last_connection", this.calculateTimeToNow(lastConnection));
        },

        alertError: function (strong, text) {
            this.model.set("uptime", "-");
            this.model.set("last_connection", "Error");
            this.model.set("iconClass", "info-icon-danger");
            this.model.set("labelClass", "label-danger");
            App.showAlert(
                "error",
                strong,
                text
            );
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
