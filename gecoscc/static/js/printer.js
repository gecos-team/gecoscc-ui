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

App.module("Printer.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.PrinterModel = App.GecosResourceModel.extend({
        resourceType: "printer",

        defaults: {
            type: "printer",
            lock: false,
            source: "gecos",
            name: "",
            description: "",
            ppdfile: "",
            brand: "",
            model: "",
            location: "",
            serial: "",
            registry: "",
            driverinstallation: "",
            duplex: "",
            extra: ""
        }
    });
});

App.module("Printer.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.PrinterForm = App.GecosFormItemView.extend({
        template: "#printer-template",
        tagName: "div",
        className: "col-sm-12",

        groupsWidget: undefined,

        events: {
            "click #submit": "saveForm",
            "click #delete": "deleteModel",
            "change input": "validate",
            "change #ppdfile": "onChangePPDFile",
            "change #installation input[type=radio]": "onChangeInstallation",
            "click #cleanfile": "cleanFile"
        },

        onChangePPDFile: function (evt) {
            var $file = $(evt.target),
                $container = $("#driver");

            if ($file.val() !== "") {
                $container.find("select").attr("disabled", true);
            } else {
                $container.find("select").attr("disabled", false);
            }
        },

        onChangeInstallation: function (evt) {
            var $radio = this.$el.find("#nodriver"),
                $container = this.$el.find("#driver"),
                $select = $container.find("select"),
                $ppdfile = this.$el.find("#ppdfile"),
                $cleanfile = this.$el.find("#cleanfile");

            if ($radio.is(":checked")) {
                $select.attr("disabled", true);
                $ppdfile.attr("disabled", true);
                $cleanfile.attr("disabled", true);
            } else {
                $container.find("select").attr("disabled", false);
                $ppdfile.attr("disabled", false);
                $cleanfile.attr("disabled", false);
            }
        },

        cleanFile: function (evt) {
            evt.preventDefault();
            $("#ppdfile").val("").trigger("change");
        },

        onRender: function () {
            this.groupsWidget = new App.Group.Views.MultiGroupWidget({
                el: this.$el.find("div#groups-widget")[0],
                checked: this.model.get("memberof")
            });
            this.groupsWidget.render();
        },

        saveForm: function (evt) {
            evt.preventDefault();
            this.saveModel($(evt.target), {
                memberof: _.bind(this.groupsWidget.getChecked, this.groupsWidget),
                name: "#name",
                serial: "#serial",
                registry: "#registry",
                brand: "#brand",
                model: "#model",
                duplex: "#ppdfile",
                // description: "#description",
                installation: "#installation"
            });
        }
    });
});
