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

App.module("Repository.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.RepositoryModel = App.GecosResourceModel.extend({
        resourceType: "repository",

        defaults: {
            type: "repository",
            lock: false,
            source: "gecos",
            name: "",
            url: "",
            distribution: "",
            deb_src: "",
            key: "",
            key_server: ""
        },

        url: function () {
            var url = "/api/repositories/";
            if (this.has("id")) {
                url += this.get("id") + '/';
            }
            return url;
        }
    });
});

App.module("Repository.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.RepositoryForm = App.GecosFormItemView.extend({
        template: "#repository-template",
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

            var that = this, isSrc;

            isSrc = function () {
                return that.$el.find("#deb_src").is(":checked");
            };

            this.saveModel($(evt.target), {
                name: "#name",
                url: "#url",
                distribution: "#distribution",
                deb_src: isSrc,
                key: "#key",
                key_server: "#key_server"
            });
        }
    });
});
