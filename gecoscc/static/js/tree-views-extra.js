/*jslint browser: true, nomen: true, unparam: true */
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

// Contains code from Fuel UX Tree - https://github.com/ExactTarget/fuelux
// Copyright (c) 2012 ExactTarget - Licensed under the MIT license

App.module("Tree.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.SelectionInfo = Marionette.ItemView.extend({
        template: "#tree-selection-template",

        selection: [],
        cache: App.createCache(),

        events: {
            "click button#selection-info-clear": "clearSelection",
            "click button#selection-info-add2group": "add2group"
        },

        getNodes: function () {
            var that = this,
                nodes = [];

            _.each(this.selection, function (id) {
                var node = that.cache.get(id);
                if (node) { nodes.push(node); }
            });

            if (nodes.length !== this.selection.length) {
                nodes = App.instances.tree.findNodes(this.selection);
                _.each(nodes, function (n) {
                    that.cache.set(n.id, n);
                });
            }

            return nodes;
        },

        serializeData: function () {
            var nodes = this.getNodes(),
                groups = [],
                that = this,
                noGroupsInSelection;

            noGroupsInSelection = _.every(nodes, function (node) {
                return (node.type !== "group" && node.type !== "ou");
            });
            if (noGroupsInSelection) {
                if (App.instances.groups && App.instances.groups.length > 0) {
                    groups = App.instances.groups.toJSON();
                } else {
                    groups = new App.Group.Models.GroupCollection();
                    groups.fetch().done(function () {
                        that.render();
                    });
                    App.instances.groups = groups;
                    noGroupsInSelection = false;
                }
            }

            return {
                noGroups: noGroupsInSelection,
                groups: groups,
                number: this.selection.length
            };
        },

        onRender: function () {
            var height = this.$el.height();
            this.$el.find("select").chosen();
            $("#ex-tree").css("margin-top", height + "px");
        },

        addIdToSelection: function (id) {
            if (!_.contains(this.selection, id)) {
                this.selection.push(id);
            }
            this.render();
        },

        removeIdFromSelection: function (id) {
            this.selection = _.reject(this.selection, function (id2) {
                return id === id2;
            });
            this.render();
        },

        clearSelection: function (evt) {
            if (evt) { evt.preventDefault(); }
            this.selection = [];
            App.tree.currentView.clearNodeSelection();
            this.render();
        },

        getSelection: function () {
            return _.clone(this.selection);
        },

        _getModel: function (type) {
            switch (type) {
            case "user":
                return App.User.Models.UserModel;
            case "computer":
                return App.Computer.Models.ComputerModel;
            case "storage":
                return App.Storage.Models.StorageModel;
            }
        },

        add2group: function (evt) {
            evt.preventDefault();
            var groupId = this.$el.find("select option:selected").val(),
                groupModel = App.instances.groups.get(groupId),
                nodes = this.getNodes(),
                promises = [],
                models = [],
                that = this;

            // 1. Add the model id to nodemembers of group
            _.each(this.selection, function (id) {
                groupModel.get("nodemembers").push(id);
            });

            // 2. Get the models
            _.each(nodes, function (n) {
                var model = App.instances.cache.get(n.id),
                    promise = $.Deferred(),
                    Model;

                if (_.isUndefined(model)) {
                    // Not cached
                    Model = that._getModel(n.type);
                    model = new Model({ id: n.id });
                    promise = model.fetch();
                    App.instances.cache.set(n.id, model);
                } else {
                    promise.resolve();
                }
                models.push(model);
                // 3. Fetch them
                promises.push(promise);
            });

            // 4. When fetched
            $.when.apply($, promises).done(function () {
                _.each(models, function (m) {
                    // 4.1. Add the groupID to the memberof
                    m.get("memberof").push(groupId);
                    // 4.2 Save the model
                    m.save();
                });
                groupModel.save();
            });

            this.clearSelection();
        }
    });

    Views.SearchResults = Marionette.ItemView.extend({
        template: "#tree-search-results-template",

        events: {
            "click .tree-leaf": "editNode",
            "click .tree-pagination": "paginate"
        },

        serializeData: function () {
            var nodes = this.collection.toJSON(),
                showPrev = this.collection.currentPage > 1,
                showNext = this.collection.currentPage < this.collection.totalPages;

            _.each(nodes, function (n) {
                n.icon = Views.iconClasses[n.type];
            });

            return {
                items: nodes,
                showPrev: showPrev,
                showNext: showNext
            };
        },

        initialize: function (options) {
            this.treeView = options.treeView;
        },

        editNode: function (evt) {
            evt.preventDefault();
            var id = $(evt.target).parents(".tree-node").first().attr("id");

            $("#tree-search").val("");
            $("#tree-close-search-btn").hide()
            App.tree.show(this.treeView);
            App.instances.router.navigate("byid/" + id, { trigger: true });
        },

        paginate: function (evt) {
            evt.preventDefault();
            var page = this.collection.currentPage,
                that = this,
                $el,
                prev;

            $el = $(evt.target);
            if (!$el.is(".tree-pagination")) {
                $el = $el.parents(".tree-pagination").first();
            }
            prev = $el.data("pagination") === "up";

            page = prev ? page - 1 : page + 1;
            this.collection.goTo(page, {
                success: function () { that.render(); }
            });
        }
    });
});
