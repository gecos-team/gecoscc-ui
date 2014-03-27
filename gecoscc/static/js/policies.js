/*jslint browser: true, vars: false, nomen: true, unparam: true */
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

App.module("Policies.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.GecosResourceModel = App.GecosResourceModel.extend({
        parse: function (response) {
            var result = _.clone(response);

            result.id = response._id;
            result.policyCollection = new Models.PolicyCollection(
                _.map(response.policies, function (value, key) {
                    return {
                        _id: key,
                        id: key,
                        values: value
                    };
                })
            );

            this.resolvePoliciesNames(result.policyCollection);

            return result;
        },

        resolvePoliciesNames: function (collection) {
            var oids;

            if (_.isUndefined(collection)) {
                collection = this.get("policyCollection");
            }

            oids = collection.map(function (p) { return p.get("id"); });
            oids = oids.join(',');
            if (oids.length === 0) { return; }

            // $.ajax("/api/policies?oids=" + oids).done(function (response) {
            $.ajax("/static/policies.json").done(function (response) {
                _.each(response.policies, function (p) {
                    var model = collection.get(p._id);

                    if (_.isUndefined(model)) { return; }
                    model.set("name", p.name);
                    model.set("schema", p.schema);
                });
            });
        }
    });

    Models.PolicyModel = Backbone.Model.extend({
        defaults: {
            name: "",
            schema: {},
            values: {}
        },

        url: function () {
//             var url = "/api/policies/";
//             if (this.has("id")) {
//                 url += this.get("id") + '/';
//             }
//             return url;
            return "/static/policies.json"; // FIXME mockup
        },

        parse: function (response) {
            var result = _.clone(response);
            result.id = response._id;
            return result;
        }
    });

    Models.PolicyCollection = Backbone.Collection.extend({
        model: Models.PolicyModel,

        url: function () {
            // return "/api/policies/?pagesize=99999";
            return "/static/policies.json"; // FIXME mockup
        },

        parse: function (response) {
            return response.policies;
        }
    });

    Models.PaginatedPolicyCollection = Backbone.Paginator.requestPager.extend({
        model: Models.PolicyModel,

        paginator_core: {
            type: "GET",
            dataType: "json",
            // url: "/api/policies/"
            url: "/static/policies.json" // FIXME mockup
        },

        paginator_ui: {
            firstPage: 1,
            currentPage: 1,
            perPage: 10,
            pagesInRange: 2,
            // 10 as a default in case your service doesn't return the total
            totalPages: 10
        },

        server_api: {
            page: function () { return this.currentPage; },
            pagesize: function () { return this.perPage; }
        },

        parse: function (response) {
            this.totalPages = response.pages;
            return response.policies;
        }
    });
});

App.module("Policies.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.PoliciesList = Marionette.ItemView.extend({
        template: "#policies-list-template",

        resource: null,

        initialize: function (options) {
            if (_.has(options, "resource")) {
                this.resource = options.resource;
            }
        },

        events: {
            "click button.btn-danger": "remove",
            "click button.btn-default": "edit",
            "click button.btn-primary": "add"
        },

        remove: function (evt) {
            evt.preventDefault();
            // TODO
        },

        edit: function (evt) {
            evt.preventDefault();
            // TODO
        },

        add: function (evt) {
            evt.preventDefault();
            // TODO
        }
    });

    Views.AllPoliciesModal = Marionette.ItemView.extend({
        template: "#policies-modal-template",

        events: {}
    });
});
