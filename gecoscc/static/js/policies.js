/*jslint browser: true, vars: false, nomen: true, unparam: true */
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

App.module("Policies.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.PolicyModel = Backbone.Model.extend({
        defaults: {
            name: "",
            schema: {},
            values: {}
        },

        url: function () {
            var url = "/api/policies/";
            if (this.has("id")) {
                url += this.get("id") + '/';
            }
            return url;
        },

        parse: function (response) {
            var result = _.clone(response);
            result.id = response._id;
            return result;
        }
    });

    Models.PolicyCollection = Backbone.Collection.extend({
        model: Models.PolicyModel
    });
});

App.module("Policies.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.PoliciesList = Marionette.ItemView.extend({
        template: "#policies-list-template"
    });
});
