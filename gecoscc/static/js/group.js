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

                if (!App.instances.groups) {
                    App.instances.groups = new App.Models.GroupCollection();
                }
                view = new App.Views.GroupTable({ model: App.instances.groups });
                App.main.show(App.instances.loader);
                App.instances.groups.fetch({
                    success: function () {
                        App.main.show(view);
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
        App.instances.router.navigate("", { trigger: true });
    });
}(Backbone));

App.module("Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.Group = Backbone.Model.extend({
        url: function () {
            var url = "/api/groups/";
            if (this.has("id")) {
                url += this.get("id") + '/';
            }
            return url;
        }
    });

    Models.GroupCollection = Backbone.Collection.extend({
        model: Models.Group,

        url: function () {
            return "/api/groups/";
        }
    });
});

App.module("Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.GroupTable = Marionette.ItemView.extend({
        template: "#groups-table-template",

        onRender: function () {
            /* Table initialisation */
            this.$el.find("table").dataTable({
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
    });
});
