/*jslint browser: true, unparam: true, nomen: true, vars: false */
/*global App, GecosUtils, gettext */

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

    Models.GroupModel = App.GecosResourceModel.extend({
        resourceType: "group",

        defaults: {
            name: "",
            groupmembers: [],
            nodemembers: []
        }
    });

    Models.GroupCollection = Backbone.Collection.extend({
        model: Models.GroupModel,

        url: function () {
            return "/api/groups/?pagesize=99999";
        },

        parse: function (response) {
            return response.nodes;
        }
    });

    Models.PaginatedGroupCollection = Backbone.Paginator.requestPager.extend({
        model: Models.GroupModel,

        paginator_core: {
            type: "GET",
            dataType: "json",
            url: "/api/groups/"
        },

        paginator_ui: {
            firstPage: 0,
            currentPage: 0,
            perPage: 16,
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
            return response.nodes;
        }
    });
});

App.module("Group.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.GroupMembers = Marionette.ItemView.extend({
        template: "#groupmembers-template",

        initialize: function (options) {
            this.groupmembers = options.groupmembers;
        },

        serializeData: function () {
            return {
                groupmembers: _.pairs(this.groupmembers)
            };
        }
    });

    Views.NodeMembers = Marionette.ItemView.extend({
        template: "#nodemembers-template",

        initialize: function (options) {
            this.nodemembers = options.nodemembers;
        },

        serializeData: function () {
            return {
                nodemembers: _.pairs(this.nodemembers)
            };
        }
    });

    Views.GroupForm = Marionette.Layout.extend({
        template: "#groups-form-template",
        tagName: "div",
        className: "col-sm-12",

        regions: {
            memberof: "#memberof",
            groupmembers: "#groupmembers",
            nodemembers: "#nodemembers"
        },

        events: {
            "click button#delete": "deleteModel",
            "click button#save": "save",
            "click button#goback": "go2table"
        },

        helperView: undefined,

        initialize: function (options) {
            this.helperView = new App.GecosFormItemView({
                model: options.model,
                el: this.el
            });
            this.helperView.resourceType = "group";
        },

        renderMembers: function (propName, View) {
            var oids = this.model.get(propName).join(','),
                aux = {},
                that = this;

            if (oids.length === 0) {
                aux[propName] = {};
                aux = new View(aux);
                this[propName].show(aux);
            } else {
                $.ajax("/api/nodes/?oids=" + oids).done(function (response) {
                    var items = response.nodes,
                        members = {},
                        view;

                    _.each(items, function (el) {
                        members[el._id] = el.name;
                    });

                    aux[propName] = members;
                    view = new View(aux);
                    that[propName].show(view);
                });
            }
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
                collection: groups,
                checked: this.model.get("memberof")
            });
            promise.done(function () {
                that.memberof.show(widget);
            });

            this.renderMembers("groupmembers", Views.GroupMembers);
            this.renderMembers("nodemembers", Views.NodeMembers);
        },

        deleteModel: function (evt) {
            this.helperView.deleteModel(evt);
        },

        save: function (evt) {
            evt.preventDefault();
            this.helperView.saveModel($(evt.target), {
                memberof: _.bind(this.memberof.currentView.getChecked, this),
                name: "#name"
            });
        },

        go2table: function (evt) {
            evt.preventDefault();
            App.instances.router.navigate("", { trigger: true });
        }
    });

    Views.GroupWidget = Marionette.ItemView.extend({
        template: "#groups-widget-template",

        checked: undefined,

        initialize: function (options) {
            if (_.has(options, "checked")) {
                this.checked = options.checked;
            }
        },

        serializeData: function () {
            var data = {},
                that = this,
                groups;

            if (this.collection) {
                if (this.unique) {
                    if (_.isUndefined(this.checked)) {
                        this.checked = "";
                    }
                }

                // Sort the groups, checked first
                groups = this.collection.toJSON();
                groups = _.sortBy(groups, function (g) {
                    return that.checked === g.id ? 0 : 1;
                });

                data = {
                    items: groups,
                    checked: this.checked
                };
            }
            return data;
        },

        onRender: function () {
            this.$el.find("select").chosen();
        },

        getChecked: function () {
            var result = this.$el.find("option:selected").val();
            if (result.length === 0) { return null; }
            return result;
        }
    });

    Views.MultiGroupWidget = Marionette.ItemView.extend({
        template: "#groups-multi-widget-template",

        groupTpl: _.template("<li><label class='group checkbox-inline'>" +
                             "<input type='checkbox'" +
                             "       id='<%= id %>'" +
                             "       <%= checked %>>" +
                             "<%= name %></label></li>"),

        checked: [],

        initialize: function (options) {
            var that = this;
            if (_.has(options, "checked") && _.isArray(options.checked)) {
                this.checked = options.checked;
            }
            this.collection = new App.Group.Models.PaginatedGroupCollection();
            this.collection.goTo(0, {
                success: function () { that.render(); }
            });
        },

        ui: {
            filter: "input.group-filter"
        },

        events: {
            "keyup @ui.filter": "filterGroups",
            "click .group-filter-btn": "cleanFilter",
            "click ul.pagination a": "goToPage",
            "change label.group input": "selectGroup"
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
                if (page >= 0 && page < total) {
                    paginator.push([page, page === current]);
                }
            }
            return {
                prev: current !== 0,
                next: current !== (total - 1),
                pages: paginator,
                showLoader: this.showLoader
            };
        },

        onRender: function () {
            var groups = this.collection.toJSON(),
                lists = { 0: [], 1: [], 2: [], 3: [] },
                that = this;

            _.each(groups, function (g, idx) {
                g.checked = _.contains(that.checked, g.id) ? "checked" : "";
                lists[idx % 4].push(that.groupTpl(g));
            });
            this.$el.find("ul.group-column").each(function (idx, ul) {
                $(ul).html(lists[idx].join(""));
            });
        },

        filterGroups: function (evt) {
            evt.preventDefault();
            // TODO
//             var filter = this.ui.filter.val();
//
//             this.$el.find("label.group").each(function (index, label) {
//                 var $label = $(label),
//                     filterReady = filter.trim().toLowerCase(),
//                     text = $label.text().trim().toLowerCase();
//                 if (filterReady.length === 0 || text.indexOf(filterReady) >= 0) {
//                     $label.parent().show();
//                 } else {
//                     $label.parent().hide();
//                 }
//             });
        },

        cleanFilter: function (evt) {
            this.ui.filter.val("");
            this.filterGroups(evt);
            this.ui.filter.focus();
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

        selectGroup: function (evt) {
            evt.preventDefault();
            var $el = $(evt.target),
                nid = $el.attr("id");

            if ($el.is(":checked")) {
                this.checked.push(nid);
            } else {
                this.checked = _.reject(this.checked, function (id) {
                    return id === nid;
                });
            }
        },

        getChecked: function () {
            return this.checked;
        }
    });
});
