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
            manufacturer: "",
            model: "",
            serial: "",
            registry: "",
            name: "",
            description: "",
            location: "",
            connection: "network",
            uri: "",
            ppd_uri: ""
        }
    });
});

App.module("Printer.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.PrinterForm = App.GecosFormItemView.extend({
        template: "#printer-template",
        tagName: "div",
        className: "col-sm-12",

        events: {
            "click #submit": "saveForm",
            "click #delete": "deleteModel",
            "change input": "validate",
            "click button.refresh": "refresh"
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
                manufacturer: "#manufacturer",
                model: "#model",
                serial: "#serial",
                registry: "#registry",
                name: "#name",
                description: "#description",
                location: "#location",
                connection: "#connection option:selected",
                uri: "#uri",
                ppd_uri: "#ppd_uri"
            });
        }
    });
});
