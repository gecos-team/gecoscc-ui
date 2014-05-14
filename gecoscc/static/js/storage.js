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

App.module("Storage.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.StorageModel = App.GecosResourceModel.extend({
        resourceType: "storage",

        defaults: {
            type: "storage",
            lock: false,
            source: "gecos",
            name: "",
            uri: "",
        },

        parse: function (response) {
            var result = _.clone(response);
            result.id = response._id;
            result.port = parseInt(response.port, 10);
            return result;
        }
    });
});

App.module("Storage.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.StorageForm = App.GecosFormItemView.extend({
        template: "#storage-template",
        tagName: "div",
        className: "col-sm-12",

        ui: {
            protocol: "select#protocol",
            port: "#port"
        },

        events: {
            "click #submit": "saveForm",
            "click #delete": "deleteModel",
            "change input": "validate",
            "click button.refresh": "refresh"
        },

        saveForm: function (evt) {
            evt.preventDefault();
            var that = this;

            this.saveModel($(evt.target), {
                name: "#name",
                uri: "#uri"
            });
        }
    });
});
