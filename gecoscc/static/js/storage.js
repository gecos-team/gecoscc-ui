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
            localpath: "",
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
            this.groupsWidget = new App.Group.Views.MultiGroupWidget({
                el: this.$el.find("div#groups-widget")[0],
                checked: this.model.get("memberof")
            });
            this.groupsWidget.render();

            this.updateConnect();
        },

        updateConnect: function () {
            var connect = this.ui.protocol.val() + "://";
//             connect += this.$el.find("#user").val() + '@';
            connect += this.$el.find("#server").val() + ':';
            connect += this.ui.port.val() + ':';
            connect += this.$el.find("#localpath").val();
            connect += " " + this.$el.find("#extraops").val();
            this.$el.find("#connect").val(connect);
        },

        saveForm: function (evt) {
            evt.preventDefault();
            var that = this;

            this.saveModel($(evt.target), {
                memberof: _.bind(this.groupsWidget.getChecked, this.groupsWidget),
                name: "#name",
                server: "#server",
                port: function () {
                    return parseInt(that.$el.find("#port").val(), 10);
                },
                extraops: "#extraops",
                protocol: "#protocol option:selected",
                localpath: "#localpath",
                mount: "#mount option:selected"
            });
        }
    });
});
