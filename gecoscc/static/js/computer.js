/*jslint browser: true, nomen: true, unparam: true, vars: false */
/*global App */

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
            this.groupsWidget = new App.Group.Views.MultiGroupWidget({
                el: this.$el.find("div#groups-widget")[0],
                checked: this.model.get("memberof")
            });
            this.groupsWidget.render();

            this.$el.find("#ohai-json").click(function (evt) {
                var $el = $(evt.target).find("span.fa");
                $el.toggleClass("fa-caret-right").toggleClass("fa-caret-down");
            });
        },

        saveForm: function (evt) {
            evt.preventDefault();
            this.saveModel($(evt.target), {
                memberof: _.bind(this.groupsWidget.getChecked, this),
                name: "#name",
                identifier: "#identifier",
                ip: "#ip",
                mac: "#mac",
                family: "#family option:selected",
                serial: "#serial",
                registry: "#registry",
                extra: "#extra"
            });
        }
    });
});
