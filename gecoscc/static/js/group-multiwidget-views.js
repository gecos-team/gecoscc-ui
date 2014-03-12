/*jslint browser: true, unparam: true, nomen: true, vars: false */
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

App.module("Group.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.GroupTags = Marionette.ItemView.extend({
        tagName: "p",

        template: "<% _.each(items, function (group) { %>\n" +
                  "    <span id='gt<%= group.id %>' class='label label-default'>\n" +
                  "        <%= group.name %> <span class='fa fa-times'></span>\n" +
                  "    </span>\n" +
                  "<% }) %>\n",

        events: {
            "click span.label": "removeFromSelection"
        },

        initialize: function (options) {
            this.widget = options.widget;
        },

        getTemplate: function () {
            return _.template(this.template);
        },

        onRender: function () {
            this.delegateEvents();
        },

        removeFromSelection: function (evt) {
            evt.preventDefault();
            var id = $(evt.target).attr("id"),
                group = this.widget.checked.get(id.substring(2));
            this.widget.checked.remove(group);
        }
    });

    Views.MultiGroupWidget = Marionette.Layout.extend({
        template: "#groups-multi-widget-template",

        regions: {
            selected: "div.selected-groups"
        },

        groupTpl: _.template("<li><label class='group checkbox-inline'>" +
                             "<input type='checkbox'" +
                             "       id='<%= id %>'" +
                             "       <%= checked %>>" +
                             "<%= name %></label></li>"),

        checked: undefined,
        filteredGroups: null,
        currentFilter: "",

        initialize: function (options) {
            var that = this,
                checked = [],
                view;

            if (_.isArray(options.checked)) {
                checked = options.checked;
            }

            this.checked = new App.Group.Models.GroupCollection();
            view = new Views.GroupTags({
                collection: this.checked,
                widget: this
            });

            this.checked.on("change", function () {
                that.selected.show(view);
            });
            this.checked.on("remove", function () {
                that.render();
            });
            _.each(checked, function (id) {
                var group = new App.Group.Models.GroupModel({ id: id });
                group.fetch();
                that.checked.add(group);
            });

            this.collection = new App.Group.Models.PaginatedGroupCollection();
            this.collection.goTo(0, {
                success: function () { that.render(); }
            });
        },

        ui: {
            filter: "input.group-filter"
        },

        events: {
            "keyup @ui.filter": "searchGroups",
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
                    paginator.push([page + 1, page === current]);
                    // + 1 so the paginator doesn't start with 0
                }
            }
            return {
                prev: current !== 0,
                next: current !== (total - 1),
                pages: paginator,
                showPaginator: _.isNull(this.filteredGroups),
                currentFilter: this.currentFilter
            };
        },

        getGroups: function () {
            if (_.isNull(this.filteredGroups)) {
                return this.collection;
            }
            return this.filteredGroups;
        },

        onRender: function () {
            var groups = this.getGroups().toJSON(),
                lists = { 0: [], 1: [], 2: [], 3: [] },
                that = this,
                checkedIds;

            checkedIds = this.checked.map(function (g) {
                return g.get("id");
            });
            _.each(groups, function (g, idx) {
                g.checked = _.contains(checkedIds, g.id) ? "checked" : "";
                lists[idx % 4].push(that.groupTpl(g));
            });
            this.$el.find("ul.group-column").each(function (idx, ul) {
                $(ul).html(lists[idx].join(""));
            });

            this.checked.trigger("change");
        },

        searchGroups: _.debounce(function (evt) {
            evt.preventDefault();
            var keyword = this.ui.filter.val().trim(),
                that = this;

            this.currentFilter = keyword;
            if (keyword.length > 0) {
                $.ajax("/api/groups/?pagesize=99999&iname=" + keyword).done(function (response) {
                    that.filteredGroups = new App.Group.Models.GroupCollection();
                    _.each(response.nodes, function (g) {
                        var group;
                        g = App.Group.Models.GroupModel.prototype.parse(g);
                        group = new App.Group.Models.GroupModel(g);
                        that.filteredGroups.add(group);
                    });
                    that.render();
                    that.ui.filter.focus().val(that.ui.filter.val()); // Set
                    // the cursor at the end of the filter input field
                });
            } else {
                this.filteredGroups = null;
                this.render();
            }
        }, 500),

        cleanFilter: function (evt) {
            this.ui.filter.val("");
            this.searchGroups(evt);
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
                page = parseInt($el.text(), 10) - 1;
                // - 1 because the paginator internally starts in 0
            }
            this.collection.goTo(page, {
                success: function () { that.render(); }
            });
        },

        selectGroup: function (evt) {
            evt.preventDefault();
            var $el = $(evt.target),
                nid = $el.attr("id"),
                group;

            if ($el.is(":checked")) {
                group = new App.Group.Models.GroupModel({ id: nid });
                group.fetch();
                this.checked.add(group);
            } else {
                group = this.checked.get(nid);
                this.checked.remove(group);
            }
        },

        getChecked: function () {
            return this.checked.map(function (g) { return g.get("id"); });
        }
    });
});
