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

    Models.OUModel = Backbone.Model.extend({
        url: function () {
            var url = "/api/ous/";
            if (this.has("id")) {
                url += this.get("id") + '/';
            }
            return url;
        }
    });
});

App.module("OU.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.OUForm = App.GecosFormItemView.extend({
        template: "#ou-template",

        events: {
            "click #submit": "saveForm",
            "change input": "validate"
        },

        saveForm: function (evt) {
            evt.preventDefault();

            if (this.validate()) {
                this.model.set({
                    name: this.$el.find("#name").val().trim(),
                    extra: this.$el.find("#extra").val().trim()
                });
                this.model.save();
            }
        }
    });
});
