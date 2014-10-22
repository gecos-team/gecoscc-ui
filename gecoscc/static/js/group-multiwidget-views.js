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
            var id = $(evt.target).attr("id") || $(evt.target).parent().attr("id"),
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
                             "</label><span class='group-list-item'>" +
                             "<a href='#byid/<%= id %>'><%= name %></a></span></li>"),

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
                var group = new App.Group.Models.GroupWithoutPoliciesModel({ id: id });
                group.fetch();
                that.checked.add(group);
            });

            this.collection = new App.Group.Models.PaginatedGroupCollection(null, { item_id: options.item_id, ou_id: options.ou_id });
            this.collection.goTo(1, {
                success: function () { that.render(); }
            });

            this.disabled = options.disabled;
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
                page,
                checkedIds,
                groups;

            for (i; i < pages; i += 1) {
                page = current - inRange + i;
                if (page > 0 && page <= total) {
                    paginator.push([page, page === current]);
                }
            }

            return {
                prev: current !== 1,
                next: current !== total,
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

            if (this.disabled) {
                this.$el.find("input").prop("disabled", true);
            }

            $(".add-groups").select2({
                multiple: true,
                initSelection: function (element, callback) {
                    var data = [];
                    _.each(that.checked.models, function (g) {
                        data.push({id: g.id, text: g.get("name")});
                    });
                    callback(data);
                },
                ajax: {
                    url: "/api/groups/",
                    dataType: 'json',
                    id : function(node) {
                        return node._id;
                    },
                    data: function (term, page) {
                        return {
                            item_id: that.options.item_id,
                            ou_id: that.options.ou_id,
                            iname: term,
                            page: page,
                            pagesize: 30
                        };
                    },
                    results: function (data, page) {
                        var nodes = data.nodes.map(function (n) {
                            return {
                                text: n.name,
                                value: n._id,
                                id: n._id
                            };
                        });
                        console.log(data);
                        return {results: nodes, more: data.nodes.length !== 0};
                    }
                }
            });
        },

        searchGroups: _.debounce(function (evt) {
            evt.preventDefault();
            var keyword = this.ui.filter.val().trim(),
                that = this,
                itemId = this.options.item_id,
                ouId = this.options.ou_id;

            this.currentFilter = keyword;
            if (keyword.length > 0) {
                $.ajax("/api/groups/?item_id=" + itemId + "&ou_id=" + ouId + "&pagesize=99999&iname=" + keyword).done(function (response) {
                    that.filteredGroups = new App.Group.Models.GroupCollection();
                    _.each(response.nodes, function (g) {
                        var group;
                        g = App.Group.Models.GroupWithoutPoliciesModel.prototype.parse(g);
                        group = new App.Group.Models.GroupWithoutPoliciesModel(g);
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
                page = parseInt($el.text(), 10);
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
                group = new App.Group.Models.GroupWithoutPoliciesModel({ id: nid });
                group.fetch();
                this.checked.add(group);
            } else {
                group = this.checked.get(nid);
                this.checked.remove(group);
            }
        },

        getChecked: function () {
            return _.rest($(".add-groups").select2('val'));
        }
    });
});
