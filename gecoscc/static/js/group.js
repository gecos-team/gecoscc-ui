/*jslint browser: true, unparam: true, nomen: true, vars: false */
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

App.module("Group.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.Group = Backbone.Model.extend({
// {
//     "memberof": "52aad006b984eb7df73da7b0",
//     "_id": "52aad006b984eb7df73da7b1",
//     "name": "group_2",
//     "groupmembers": [
//         "52aad006b984eb7df73da7b2",
//         "52aad006b984eb7df73da7b3",
//         "52aad006b984eb7df73da7b4",
//         "52aad006b984eb7df73da7b5",
//         "52aad006b984eb7df73da7b6",
//         "52aad006b984eb7df73da7b7"
//     ],
//     "nodemembers": [
//         "52aad005b984eb7df73da3d5",
//         "52aad005b984eb7df73da3d3",
//         "52aad005b984eb7df73da4ab",
//         "52aad006b984eb7df73da762",
//         "52aad005b984eb7df73da4fa"
//     ]
// }

        url: function () {
            var url = "/api/groups/";
            if (this.has("id")) {
                url += this.get("id") + '/';
            }
            return url;
        },

        parse: function (response) {
            var result = _.clone(response);
            result.id = response._id;
            delete result._id;
            return result;
        }
    });

    Models.GroupCollection = Backbone.Collection.extend({
        model: Models.Group,

        url: function () {
            return "/api/groups/?pagesize=1000";
        },

        parse: function (response) {
            return response.groups;
        }
    });
});

App.module("Group.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.GroupRow = Marionette.ItemView.extend({
        template: "#groups-row-template",

        tagName: "tr",

        events: {
            "click button.edit-group": "edit",
            "click button.btn-danger": "deleteModel"
        },

        edit: function (evt) {
            evt.preventDefault();
            var id = this.$el.find("td").first().attr("id");
            App.instances.router.navigate("group/" + id, { trigger: true });
        },

        deleteModel: function (evt) {
            evt.preventDefault();
            var that = this;

            GecosUtils.confirmModal.find("button.btn-danger")
                .off("click")
                .on("click", function (evt) {
                    that.model.destroy({
                        success: function () {
                            App.instances.groups.fetch();
                        }
                    });
                    GecosUtils.confirmModal.modal("hide");
                });
            GecosUtils.confirmModal.modal("show");
        }
    });

    Views.GroupTable = Marionette.CompositeView.extend({
        template: "#groups-table-template",
        itemView: Views.GroupRow,
        itemViewContainer: "tbody",

        onRender: function () {
            /* Table initialisation */
            var $table = this.$el.find("table");

            if ($table.find("tr").length > 0) {
                $table.dataTable({
                    sDom: "<'row'<'col-md-8'l><'col-md-4'f>r>t<'row'<'col-md-8'i><'col-md-4'p>>",
                    sPaginationType: "bootstrap",
                    oLanguage: {
                        sLengthMenu: "_MENU_ registros por página",
                        oAria: {
                            sSortAscending: ": activar para odernar ascendentemente la columna",
                            sSortDescending: ": activar para odernar descendentemente la columna"
                        },
                        oPaginate: {
                            sFirst: "Primero",
                            sLast: "Último",
                            sPrevious: "Anterior",
                            sNext: "Siguiente"
                        },
                        sEmptyTable: "No hay datos disponibles en la tabla",
                        sInfo: "Mostrando de _START_ a _END_ de _TOTAL_ registros",
                        sInfoEmpty: "Mostrando de 0 a 0 de 0 registros",
                        sInfoFiltered: "(filtrados de un total de _MAX_ registros)",
                        // sInfoPostFix: "All records shown are derived from real information.",
                        // sInfoThousands: ",",
                        sLoadingRecords: "Cargando...",
                        sProcessing: "Procesando...",
                        sSearch: "Buscar:",
                        // sUrl: "http://www.sprymedia.co.uk/dataTables/lang.txt",
                        sZeroRecords: "Ningún registro que encaje encontrado"
                    }
                });
            }
        }
    });

    Views.GroupForm = Marionette.Layout.extend({
        template: "#groups-form-template",

        regions: {
            memberof: "#memberof"
        },

        events: {
            "click button#delete": "deleteModel",
            "click button#save": "save",
            "click button#goback": "go2table",
        },

        onRender: function () {
            var that = this,
                groups,
                widget,
                promise;

            if (App.instances.groups && App.instances.groups.length > 0) {
                groups = App.instances.groups;
                promise = $.Deferred();
                promise.resolve();
            } else {
                groups = new App.Group.Models.GroupCollection();
                promise = groups.fetch();
            }

            widget = new Views.GroupWidget({
                collection: groups
            });
            promise.done(function () {
                that.memberof.show(widget);
            });
        },

        deleteModel: function (evt) {
            evt.preventDefault();
            var that = this;

            GecosUtils.confirmModal.find("button.btn-danger")
                .off("click")
                .on("click", function (evt) {
                    that.model.destroy({
                        success: function () {
                            App.instances.router.navigate("", { trigger: true });
                        }
                    });
                    GecosUtils.confirmModal.modal("hide");
                });
            GecosUtils.confirmModal.modal("show");
        },

        save: function (evt) {
            evt.preventDefault();
            // TODO
            this.model.save({
                success: function () {
                    App.instances.router.navigate("", { trigger: true });
                }
            });
        },

        go2table: function (evt) {
            evt.preventDefault();
            App.instances.router.navigate("", { trigger: true });
        }
    });

    Views.GroupWidget = Marionette.ItemView.extend({
        template: "#groups-widget-template",

        unique: true,
        checked: undefined,

        ui: {
            "filter": "input.group-filter"
        },

        events: {
            "keyup @ui.filter": "filterGroups",
            "click .group-filter-btn": "filterGroups"
        },

        serializeData: function () {
            var data = {},
                inputType = "checkbox";

            if (this.collection) {
                if (this.unique) {
                    inputType = "radio";
                    if (_.isUndefined(this.checked)) {
                        this.checked = "";
                    }
                } else if (_.isUndefined(this.checked)) {
                    this.checked = [];
                }
                data = {
                    items: this.collection.toJSON(),
                    inputType: inputType,
                    checked: this.checked
                };
            }
            return data;
        },

        filterGroups: function (evt) {
            evt.preventDefault();
            var filter = this.ui.filter.val();

            this.$el.find("label.group").each(function (index, label) {
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
