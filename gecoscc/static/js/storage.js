/*jslint browser: true, nomen: true, unparam: true, vars: false */
/*global App */

/*
* Copyright 2013, Junta de Andalucia
* http://www.juntadeandalucia.es/
*
* Authors:
*   Alberto Beiztegui <albertobeiz@gmail.com>
*   Alejandro Blanco <alejandro.b.e@gmail.com>
*
* All rights reserved - EUPL License V 1.1
* https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
*/

App.module("Storage.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.StorageModel = App.Policies.Models.GecosResourceModel.extend({
        resourceType: "storage",

        defaults: {
            type: "storage",
            lock: false,
            source: "gecos",
            name: "",
            uri: "",
            isEditable: undefined
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
            "click button.refresh": "refresh",
            "click #cut": "cutModel"
        },

        onBeforeRender: function () {
            var path = this.model.get("path");

            if (this.model.get("isEditable") !== undefined) { return; }

            if (path.split(',')[0] === "undefined") {
                this.model.set("isEditable", true);
            } else {
                this.getDomainAttrs();
            }
        },

        onRender: function () {
            this.canMove();
            if (!_.isUndefined(this.model.id)) {
                this.$el.find("#name").attr('disabled', 'disabled');
            }

            if (!this.model.get("isEditable")) {
                this.$el.find("textarea,input,select").prop("disabled", true).prop("placeholder", '');
            }
        },

        saveForm: function (evt) {
            evt.preventDefault();

            this.saveModel($(evt.target), {
                name: "#name",
                uri: "#uri"
            });
        }
    });
});
