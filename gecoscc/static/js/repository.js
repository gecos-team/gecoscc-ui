/*jslint browser: true, nomen: true, unparam: true, vars: false */
/*global App */

/*
* Copyright 2013, Junta de Andalucia
* http://www.juntadeandalucia.es/
*
* Authors:
*   Alberto Beiztegui <albertobeiz@gmail.com>
*   Alejandro Blanco <alejandro.b.e@gmail.com>
*   Emilio Sanchez <emilio.sanchez@gmail.com>
*
* All rights reserved - EUPL License V 1.1
* https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
*/

App.module("Repository.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.RepositoryModel = App.Policies.Models.GecosResourceModel.extend({
        resourceType: "repository",

        defaults: {
            type: "repository",
            lock: false,
            source: "gecos",
            name: "",
            uri: "",
            distribution: "",
            components: [],
            deb_src: "",
            repo_key: "",
            key_server: "",
            isEditable: undefined
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

            var that = this, isSrc, getComponents;

            isSrc = function () {
                return that.$el.find("#deb_src").is(":checked");
            };

            getComponents = function () {
                return that.$el.find("#components").val().split(/ *, */);
            };

            this.saveModel($(evt.target), {
                name: "#name",
                uri: "#uri",
                distribution: "#distribution",
                deb_src: isSrc,
                repo_key: "#repo_key",
                components: getComponents,
                key_server: "#key_server"
            });
        }
    });
});
