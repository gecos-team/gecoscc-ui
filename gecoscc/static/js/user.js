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

App.module("User.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.UserModel = Backbone.Model.extend({});
});

App.module("User.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.UserForm = Marionette.ItemView.extend({
        template: "#user-template",

        events: {
            "keyup #permission-filter": "permissionFilter",
            "click #permission-filter-btn": "permissionFilter"
        },

        permissionFilter: function (evt) {
            var filter = $(evt.target);
            if (filter.is("input")) {
                filter = filter.val();
            } else {
                filter = filter.parents('div.input-group').find("input").val();
            }
            $("label.permission").each(function (index, label) {
                var $label = $(label),
                    filterReady = filter.trim().toLowerCase(),
                    text = $label.text().trim().toLowerCase();
                if (filterReady.length === 0 || text.indexOf(filterReady) >= 0) {
                    $label.parent().show();
                } else {
                    $label.parent().hide();
                }
            });
        }
    });
});
