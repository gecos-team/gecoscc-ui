/*jslint browser: true, vars: false, nomen: true, unparam: true */
/*global App, gettext */

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

App.module("Inheritance.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.InheritanceList = Marionette.ItemView.extend({
        template: "#inheritance-list-template",
        tagName: "div",
        className: "col-sm-12",

        resource: null,

        initialize: function (options) {
            if (_.has(options, "resource")) {
                this.resource = options.resource;
            }
            this.collection = this.resource.get('inheritanceCollection');
        },
        
        serializeData: function () {
            return {items: this.collection,
                    resource: this.resource};
        },
    });
});