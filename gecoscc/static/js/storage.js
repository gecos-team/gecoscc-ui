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
            server: "",
            port: 21,
            protocol: "ftp",
            devicepath: "",
            mount: "fstab",
            extraops: ""
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
            "keyup input": "updateConnect",
            "change @ui.protocol": "updateConnect",
            "change @ui.port": "updateConnect"
        },

        onRender: function () {
            var groups, promise;

            if (App.instances.groups && App.instances.groups.length > 0) {
                groups = App.instances.groups;
                promise = $.Deferred();
                promise.resolve();
            } else {
                groups = new App.Group.Models.GroupCollection();
                promise = groups.fetch({
                    success: function () {
                        App.instances.groups = groups;
                    }
                });
            }

            this.groupsWidget = new App.Group.Views.GroupWidget({
                el: this.$el.find("div#groups-widget")[0],
                collection: groups,
                checked: this.model.get("memberof"),
                unique: false
            });
            promise.done(_.bind(function () {
                this.groupsWidget.render();
            }, this));

            this.updateConnect();
        },

        updateConnect: function () {
            var connect = this.ui.protocol.val() + "://";
//             connect += this.$el.find("#user").val() + '@';
            connect += this.$el.find("#server").val() + ':';
            connect += this.ui.port.val() + ':';
            connect += this.$el.find("#devicepath").val();
            connect += " " + this.$el.find("#extraops").val();
            this.$el.find("#connect").val(connect);
        }
    });
});
