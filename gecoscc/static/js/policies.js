/*jslint browser: true, vars: false, nomen: true, unparam: true */
/*global App, gettext */

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
            this.resolvePoliciesNames(result.policyCollection, result.path);

            return result;
        },

        resolvePoliciesNames: function (collection, path) {
            var that = this,
                oids,
                url,
                ou_id;

            if (_.isUndefined(collection)) {
                collection = this.get("policyCollection");
            }
            if (!collection.hasUnknownPolicies()) { return; }

            oids = collection.getOids().join(',');
            url = "/api/policies/?oids=" + oids;
            ou_id = _.last(path.split(','));
            if (ou_id) {
                url += "&ou_id=" + ou_id;
            }
            if (this.has('id')) {
                url += "&item_id=" + this.id;
            }
            $.ajax(url).done(function (response) {
                _.each(response.policies, function (p) {
                    var model = collection.get(p._id);

                    if (_.isUndefined(model)) { return; }
                    model.set("name", p.name);
                    model.set("support_os", p.support_os);
                    model.set("schema", p.schema);
                });
                that.trigger("policiesloaded");
            });
        },

        removePolicy: function (id) {
            this.get("policyCollection").remove(id);
            delete this.get("policies")[id];
            this.save();
            App.instances.staging.toModify.push(this.get("id"));
        },

        addPolicy: function (policyModel, values) {
            this.get("policyCollection").add(policyModel);
            this.get("policies")[policyModel.get("id")] = values;
            this.save();
            App.instances.staging.toModify.push(this.get("id"));
        },

        getDomainId: function () {
            return this.get("path").split(",")[2] || this.get("id");
        }
    });

    Models.PolicyModel = Backbone.Model.extend({
        defaults: {
            name: "",
            schema: {},
            values: {}
        },

        url: function () {
            var url = "/api/policies/";
            if (this.has("id")) {
                url += this.get("id") + '/?';
            }
            if (this.has("ou_id")) {
                url += "ou_id=" + this.get("ou_id") + '&';
            }
            if (this.has("item_id")) {
                url += "item_id=" + this.get("item_id");
            }
            return url;
        },

        parse: function (response) {
            var result = _.clone(response);
            result.id = response._id;
            return result;
        }
    });

    Models.PolicyCollection = Backbone.Collection.extend({
        model: Models.PolicyModel,

        url: "/api/policies/?pagesize=99999",

        parse: function (response) {
            return response.policies;
        },

        hasUnknownPolicies: function () {
            return this.some(function (p) { return p.get("name") === ""; });
        },

        getOids: function () {
            return this.map(function (p) { return p.get("id"); });
        }
    });

    Models.PaginatedPolicyCollection = Backbone.Paginator.requestPager.extend({
        model: Models.PolicyModel,

        paginator_core: {
            type: "GET",
            dataType: "json",
            url: "/api/policies/"
        },

        paginator_ui: {
            firstPage: 1,
            currentPage: 1,
            perPage: 8,
            pagesInRange: 3,
            // 10 as a default in case your service doesn't return the total
            totalPages: 10
        },

        server_api: {
            target: function () { return this.resource.resourceType; },
            ou_id: function () { return _.last(this.resource.get("path").split(',')); },
            item_id: function () { return this.resource.id; },
            page: function () { return this.currentPage; },
            pagesize: function () { return this.perPage; }
        },

        parse: function (response) {
            this.totalPages = response.pages;
            return response.policies;
        }
    });

    Models.SearchPolicyCollection = Models.PaginatedPolicyCollection.extend({
        initialize: function (options) {
            if (!_.isString(options.keyword)) {
                throw "Search collections require a keyword attribute";
            }
            this.keyword = options.keyword;
            if (!_.isObject(options.resource)) {
                throw "Search collections require a resource attribute";
            }
            this.resource = options.resource;
        },

        paginator_core: {
            type: "GET",
            dataType: "json",
            url: function () {
                return "/api/policies/?iname=" + this.keyword;
            }
        }
    });
});

App.module("Policies.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.PoliciesList = Marionette.ItemView.extend({
        template: "#policies-list-template",

        resource: null,
        addPolicyBtnView: null,
        addPolicyListView: null,

        initialize: function (options) {
            if (_.has(options, "resource")) {
                this.resource = options.resource;
            }
        },

        events: {
            "click table#policies-table button.btn-danger": "remove",
            "click table#policies-table button.btn-default": "edit",
            "click table#policies-table button.btn-info": "edit",
            "click button#add-policy": "add"
        },

        getPolicyUrl: function (id) {
            var url = ["ou", _.last(this.resource.get("path").split(','))];
            url.push(this.resource.resourceType);
            url.push(this.resource.get("id"));
            url.push("policy");
            if (!_.isUndefined(id)) {
                url.push(id);
            }
            return url.join('/');
        },

        remove: function (evt) {
            evt.preventDefault();
            var id = $(evt.target).parents("tr").first().attr("id");
            this.resource.removePolicy(id);
            this.render();
            App.instances.tree.trigger("change");
        },

        edit: function (evt) {
            evt.preventDefault();
            var id = $(evt.target).parents("tr").first().attr("id");
            App.instances.router.navigate(this.getPolicyUrl(id), { trigger: true });
        },

        add: function (evt) {
            App.instances.router.navigate(this.getPolicyUrl(), { trigger: true });
        },
        serializeData: function () {
            return {items: this.collection.toJSON(),
                    resource: this.resource};
        }
    });

    Views.AllPoliciesWidget = Marionette.ItemView.extend({
        template: "#policies-add-template",
        tagName: "div",
        className: "col-sm-12",

        events: {
            "click ul.pagination a": "goToPage",
            "click button.add-policy-btn": "add",
            "click button#cancel": "cancel",
            "click button#newpolicy-filter-btn": "filter",
            "click button#policy-close-search-btn": "clearSearch",
            "keyup #newpolicy-filter": "checkEnterKey"
        },

        resource: undefined,

        initialize: function (options) {
            var that = this;

            if (_.has(options, "resource")) {
                this.resource = options.resource;
            } else {
                throw "A reference to the resource is required";
            }
            this.collection = new App.Policies.Models.SearchPolicyCollection({
                resource: this.resource,
                keyword: ""
            });
            this.collection.goTo(1, {
                success: function () { that.render(); }
            });
        },

        serializeData: function () {
            var paginator = [],
                inRange = this.collection.pagesInRange,
                pages = inRange * 2 + 1,
                current = this.collection.currentPage,
                total = this.collection.totalPages,
                i = 0,
                page;

            for (i; i < pages; i += 1) {
                page = current - inRange + i;
                if (page > 0 && page <= total) {
                    paginator.push([page, page === current]);
                }
            }

            return {
                items: this.collection.toJSON(),
                totalPages: total,
                resource: this.resource.toJSON(),
                initial: current > inRange + 1,
                final: current < total - inRange,
                prev: current !== 1,
                next: current !== total,
                pages: paginator,
                showPaginator: paginator.length > 0,
                currentFilter: this.collection.keyword
            };
        },

        goToPage: function (evt) {
            evt.preventDefault();
            var $el = $(evt.target),
                that = this,
                page;

            if ($el.parent().is(".disabled")) { return; }
            if ($el.is(".previous")) {
                page = this.collection.currentPage - 1;
            } else if ($el.is(".next")) {
                page = this.collection.currentPage + 1;
            } else {
                page = parseInt($el.text(), 10);
            }
            this.collection.goTo(page, {
                success: function () { that.render(); }
            });
        },

        getUrl: function () {
            var containerid = _.last(this.resource.get("path").split(',')),
                url = "ou/" + containerid + '/' + this.resource.resourceType +
                      '/' + this.resource.get("id");
            return url;
        },

        add: function (evt) {
            evt.preventDefault();
            var id = $(evt.target).parents("li").first().attr("id"),
                url = this.getUrl();

            url += "/policy/" + id;
            App.instances.router.navigate(url, { trigger: true });
        },

        cancel: function (evt) {
            evt.preventDefault();
            App.instances.router.navigate(this.getUrl(), { trigger: true });
            $("#policy-tab a").tab("show");
        },

        filter: function (evt) {
            evt.preventDefault();
            var that = this,
                keyword = $(evt.target).parents(".input-group").find("input").val().trim();
            this.collection = new App.Policies.Models.SearchPolicyCollection({resource: this.resource,
                                                                              keyword: keyword});
            this.collection.goTo(1, {
                success: function () {
                    that.render();
                    if (keyword) {
                        $("#policy-close-search-btn").show();
                    }
                }
            });
        },

        checkEnterKey: function (evt) {
            evt.preventDefault();
            if (evt.which === 13) {
                this.filter(evt);
            }
        },

        clearSearch: function (evt) {
            evt.preventDefault();
            $(evt.target).parents(".input-group").find("input").val("");
            this.filter(evt);
        }
    });
});
