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
            printtype: "laser",
            brand: "",
            model: "",
            serial: "",
            registry: "",
            name: "",
            description: "",
            location: "",
            connection: "network",
            printerpath: "",
            driver: "auto",
            driverBrand: "",
            driverModel: "",
            driverFile: "", // FIXME mockup
            pageSize: "A4",
            quality: "medium",
            paperTray: "1", // FIXME mockup
            duplex: false
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
            "click button.refresh": "refresh",
            "change #ppdfile": "onChangePPDFile",
            "change #installation input[type=radio]": "onChangeInstallation",
            "click #cleanfile": "cleanFile"
        },

        onRender: function () {
            this.groupsWidget = new App.Group.Views.MultiGroupWidget({
                el: this.$el.find("div#groups-widget")[0],
                checked: this.model.get("memberof")
            });
            this.groupsWidget.render();
        },

        onChangePPDFile: function (evt) {
            var $file = $(evt.target),
                $container = this.$el.find("#driver");

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
            this.$el.find("#ppdfile").val("").trigger("change");
        },

        saveForm: function (evt) {
            evt.preventDefault();
            var that = this,
                getDriver,
                isDuplex;

            getDriver = function () {
                return that.$el.find("#installation input:checked").val();
            };

            isDuplex = function () {
                return that.$el.find("#duplex").is(":checked");
            };

            this.saveModel($(evt.target), {
                printtype: "#type option:selected",
                brand: "#brand",
                model: "#model",
                serial: "#serial",
                registry: "#registry",
                name: "#name",
                description: "#description",
                location: "#location",
                connection: "#connection option:selected",
                printerpath: "#path",
                driver: getDriver,
                driverBrand: "#printerBrand option:selected",
                driverModel: "#printersA option:selected", // FIXME mockup
                driverFile: "#ppdfile", // TODO probably not
                memberof: _.bind(this.groupsWidget.getChecked, this.groupsWidget),
                pageSize: "#pageSize option:selected",
                quality: "#resolution option:selected",
                paperTray: "#paper option:selected",
                duplex: isDuplex
            });
        }
    });
});
