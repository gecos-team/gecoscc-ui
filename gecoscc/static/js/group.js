/*jslint browser: true, unparam: true, nomen: true, vars: false */
/*global App:true, Backbone */

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

var App;

(function (Backbone) {
    "use strict";
    var Router,
        Loader;

    App = new Backbone.Marionette.Application();

    // To store references to root instances
    App.instances = {};

    App.addRegions({
        // main
        main: "#viewport-main"
    });

    Loader = Backbone.Marionette.ItemView.extend({
        render: function () {
            this.$el.html('<p style="font-size: 3em;">' +
                '<span class="fa fa-spin fa-spinner"></span> Loading...</p>');
            return this;
        }
    });

    App.instances.loader = new Loader();

    Router = Backbone.Marionette.AppRouter.extend({
        appRoutes: {
            "": "loadTable"
//             "ou/:containerid/user": "newUser",
//             "ou/:containerid/user/:userid": "loadUser",
//             "ou/:containerid/ou": "newOU",
//             "ou/:containerid/ou/:ouid": "loadOU"
        },

        controller: {
            loadTable: function () {
                var view;
                App.main.show(App.instances.loader);

                if (!App.instances.groups) {
                    App.instances.groups = new App.Models.GroupCollection();
                }
                App.instances.groups
                    .off("change")
                    .on("change", function () {
                        App.main.show(view);
                    });

                view = new App.Views.GroupTable({
                    collection: App.instances.groups
                });
                App.instances.groups.fetch({
                    success: function () {
                        App.instances.groups.trigger("change");
                    }
                });
            }
        }
    });

    App.instances.router = new Router();

    App.on('initialize:after', function () {
        if (Backbone.history) {
            Backbone.history.start();
        }
        App.instances.router.controller.loadTable();
    });
}(Backbone));

App.module("Models", function (Models, App, Backbone, Marionette, $, _) {
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
            return "/api/groups/";
        },

        parse: function (response) {
            return response.groups;
        }
    });
});

App.module("Views", function (Views, App, Backbone, Marionette, $, _) {
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
            // TODO
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

    Views.GroupTable = Marionette.CollectionView.extend({
        itemView: Views.GroupRow,

        initialize: function () {
            this.template = $("#groups-table-template").html();
        },

        appendBuffer: function (collectionView, buffer) {
            var $table = $(this.template);
            $table.find("tbody").append(buffer);
            collectionView.$el.html($table);
        },

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
});
