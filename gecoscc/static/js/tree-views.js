/*jslint browser: true, nomen: true, unparam: true */
/*global App, gettext, GecosUtils */

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

    var treeContainerPre =
            '<div class="tree-container tree-node" style="display: block;" id="<%= id %>" data-path="<%= path %>">\n' +
            '    <div class="tree-container-header">\n' +
            '        <div class="tree-highlight">\n' +
            '            <span class="opener fa fa-<%= controlIcon %>-square-o"></span><span class="fa fa-group"></span>\n' +
            '            <div class="tree-name"><%= name %> <span class="extra-opts fa fa-caret-right"></span></div>\n' +
            '            <input type="checkbox" class="tree-selection">\n' +
            '        </div>\n' +
            '    </div>\n' +
            '    <div class="tree-container-content" <% if (closed) { print(\'style="display: none;"\'); } %>>\n',
        treeContainerPost =
            '    </div>\n' +
            '</div>\n',
        emptyContainer =
            '<div class="tree-leaf tree-node" style="display: block;" id="<%= id %>">\n' +
            '    <div class="tree-name"><a href="#ou/<%= id %>/new">\n' +
            '        <span class="fa fa-plus"></span> ' + gettext('Add new') + '\n' +
            '    </a></div>\n' +
            '</div>',
        treeItem =
            '<div class="tree-leaf tree-node" style="display: block;" id="<%= id %>">\n' +
            '    <div class="tree-highlight">\n' +
            '        <span class="fa fa-<%= icon %>"></span>\n' +
            '        <div class="tree-name"><%= name %></div>\n' +
            '        <input type="checkbox" class="tree-selection">\n' +
            '    </div>\n' +
            '</div>\n',
        paginationItem =
            '<div class="tree-pagination tree-node" style="display: block;" data-pagination="<%= type %>">\n' +
            '    <span class="fa fa-chevron-<%= type %>"></span>\n' +
            '    <div class="tree-name">' + gettext('More') + '</div>\n' +
            '</div>\n',
        emptyTree =
            '<a href="#newroot">\n' +
            '    <span class="fa fa-plus"></span> ' + gettext('Add new root OU') + '\n' +
            '</a>\n',
        extraOpts =
            '<div class="tree-extra-options">\n' +
            '    <ul class="nav nav-pills nav-stacked">\n' +
            '        <li><a href="#ou/<%= ouId %>/new">\n' +
            '            <span class="fa fa-plus"></span> ' + gettext('Add new') + '\n' +
            '        </a></li>\n' +
            '        <li><a href="#" class="text-danger">\n' +
            '            <span class="fa fa-times"></span> ' + gettext('Delete') + '\n' +
            '        </a></li>\n' +
            '    </ul>\n' +
            '</div>\n';

    Views.iconClasses = {
        ou: "group",
        user: "user",
        computer: "desktop",
        printer: "print",
        group: "link",
        storage: "hdd-o"
    };

    Views.NavigationTree = Marionette.ItemView.extend({
        templates: {
            containerPre: _.template(treeContainerPre),
            containerPost: _.template(treeContainerPost),
            emptyContainer: _.template(emptyContainer),
            item: _.template(treeItem),
            pagItem: _.template(paginationItem),
            emptyTree: _.template(emptyTree),
            extraOpts: _.template(extraOpts)
        },

        selectionInfoView: undefined,
        activeNode: null,

        events: {
            "click a": "stopPropagation",
            "click .tree-container-header": "editNode",
            "click .tree-leaf": "editNode",
            "click .tree-pagination": "paginate",
            "click .tree-container-header .opener": "openContainer",
            "click .tree-name .extra-opts": "showContainerMenu",
            "click .tree-selection": "selectNode"
        },

        initialize: function () {
            var $search = $("#tree-search");

            this.selectionInfoView = new Views.SelectionInfo({
                el: $("#tree-selection-info")[0]
            });
            $("#tree-search-btn")
                .off("click")
                .on("click", function (evt) {
                    evt.preventDefault();
                    var keyword = $search.val().trim();
                    App.instances.router.navigate("search/" + keyword,
                                                  { trigger: true });
                });
        },

        _loader: function (size) {
            size = size || 1;
            return "<p style='font-size: " + size + "em;'><span class='fa " +
                "fa-spinner fa-spin'></span> " + gettext("Loading") +
                "...</p>";
        },

        render: function () {
            this.isClosed = false;
            this.triggerMethod("before:render", this);
            this.triggerMethod("item:before:render", this);

            var tree = this.model.toJSON(),
                html;

            if (_.isUndefined(tree)) {
                // Empty tree
                html = this.templates.emptyTree({});
            } else if (_.keys(tree).length > 0) {
                html = this.recursiveRender(tree);
            } else {
                html = this._loader(2.5);
            }
            this.$el.html(html);
            this.renderSelection();

            this.bindUIElements();
            this.delegateEvents(this.events);
            this.triggerMethod("render", this);
            this.triggerMethod("item:rendered", this);

            return this;
        },

        renderSelection: function () {
            var oids = this.selectionInfoView.getSelection(),
                that = this;

            _.each(oids, function (id) {
                var $checkbox = that.$el.find('#' + id).find("input.tree-selection").first();
                $checkbox.attr("checked", true);
                $checkbox.parent().parent().addClass("multiselected");
            });
            if (!_.isNull(this.activeNode)) {
                this.highlightNodeById(this.activeNode);
            }
        },

        recursiveRender: function (node, root) {
            var json = _.pick(node, "name", "type", "id", "path"),
                ouData,
                treeNode,
                html;

            if (json.type === "ou") {
                if (_.isUndefined(root)) { root = this.model.get("tree"); }
                treeNode = root.first({ strategy: 'breadth' }, function (n) {
                    return n.model.id === json.id;
                });

                if (_.isUndefined(treeNode)) {
                    json.closed = true; // Unloaded node, show it closed
                } else {
                    json.closed = treeNode.model.closed;
                }
                ouData = this.prepareRenderOUData(treeNode);
                json.controlIcon = json.closed ? "plus" : "minus";

                html = this.renderOU(json, ouData, treeNode);
            } else {
                // It's a regular node
                json.icon = Views.iconClasses[json.type];
                html = this.templates.item(json);
            }

            return html;
        },

        prepareRenderOUData: function (treeNode) {
            var data = {
                    showPrev: false,
                    showNext: false,
                    children: []
                },
                paginatedChildren;

            if (_.isUndefined(treeNode)) { return data; }

            if (treeNode.model.status === "paginated") {
                paginatedChildren = treeNode.model.paginatedChildren;
                data.children = paginatedChildren.toJSON();
                data.showPrev = paginatedChildren.currentPage > 0;
                data.showNext = paginatedChildren.currentPage < paginatedChildren.totalPages - 1;
            } else if (treeNode.model.status === "meta-only") {
                data.children = _.map(treeNode.children, function (child) {
                    return child.model;
                });
                data.showNext = true;
            } else {
                throw "The node has the invalid status: " + treeNode.model.status;
            }

            return data;
        },

        renderOU: function (json, data, treeNode) {
            var html = this.templates.containerPre(json),
                that = this;

            if (data.children.length > 0) {
                if (data.showPrev) {
                    html += this.templates.pagItem({ type: "up" });
                }
                _.each(data.children, function (child) {
                    html += that.recursiveRender(child, treeNode);
                });
                if (data.showNext) {
                    html += this.templates.pagItem({ type: "down" });
                }
            } else {
                html += this.templates.emptyContainer(json);
            }

            return html + this.templates.containerPost(json);
        },

        stopPropagation: function (evt) {
            evt.stopPropagation();
        },

        editNode: function (evt) {
            var $el = $(evt.target).parents(".tree-node").first(),
                that = this,
                node,
                parentId;

            this.hideContainerMenu();
            this.activeNode = $el.attr("id");
            this.highlightNodeById(this.activeNode);
            parentId = $el.parents(".tree-container").first().attr("id");
            if (_.isUndefined(parentId)) { parentId = "root"; }
            node = this.model.get("tree").first({ strategy: 'breadth' }, function (n) {
                return n.model.id === that.activeNode;
            });

            if (node) {
                App.instances.router.navigate("ou/" + parentId + "/" + node.model.type + "/" + this.activeNode, {
                    trigger: true
                });
            } else {
                App.instances.router.navigate("byid/" + this.activeNode, {
                    trigger: true
                });
            }
        },

        paginate: function (evt) {
            var $el = $(evt.target).parents(".tree-pagination").first(),
                prev = $el.data("pagination") === "up",
                that = this,
                node,
                page,
                searchId,
                id;

            $el = $el.parents(".tree-container").first();
            id = $el.attr("id");
            node = this.model.get("tree").first(function (obj) {
                return obj.model.id === id;
            });

            if (node.model.status === "paginated") {
                page = node.model.paginatedChildren.currentPage;
                page = prev ? page - 1 : page + 1;
                node.model.paginatedChildren.goTo(page, {
                    success: function () { that.model.trigger("change"); }
                });
            } else {
                searchId = $el.find(".tree-container").first().attr("id");
                this.model.loadFromPath(node.model.path + ',' + id, searchId);
            }
        },

        _openContainerAux: function ($el, $content, opened) {
            var node = this.model.get("tree"),
                id = $el.attr("id"),
                path = $el.data("path");

            node = node.first(function (obj) {
                return obj.model.id === id;
            });

            if (!_.isUndefined(node)) {
                node.model.closed = !opened;
            } else {
                $content.html(this._loader());
                this.model.loadFromPath(path + ',' + id);
            }
        },

        openContainer: function (evt) {
            evt.stopPropagation();
            var $el = $(evt.target).parents(".tree-container").first(),
                $treeFolderContent = $el.find('.tree-container-content').first(),
                classToTarget = '.fa-minus-square-o',
                classToAdd = 'fa-plus-square-o';

            this.hideContainerMenu();
            if ($el.find('.tree-container-header').first().find('.fa-minus-square-o').length > 0) {
                this._openContainerAux($el, $treeFolderContent, false);
                $treeFolderContent.hide();
            } else {
                classToTarget = '.fa-plus-square-o';
                classToAdd = 'fa-minus-square-o';
                this._openContainerAux($el, $treeFolderContent, true);
                $treeFolderContent.show();
            }

            $el.find(classToTarget).first()
                .removeClass('fa-plus-square-o fa-minus-square-o')
                .addClass(classToAdd);
        },

        _deleteOU: function () {
            var model = new App.OU.Models.OUModel({ id: this });
            model.destroy({
                success: function () {
                    App.instances.tree.reloadTree();
                }
            });
        },

        showContainerMenu: function (evt) {
            evt.stopPropagation();
            var $el = $(evt.target),
                ouId = $el.parents(".tree-container").first().attr("id"),
                $html = $(this.templates.extraOpts({ ouId: ouId })),
                closing = $el.is(".fa-caret-down"),
                that = this;

            this.hideContainerMenu();
            if (closing) { return; }
            $el.removeClass("fa-caret-right").addClass("fa-caret-down");
            $html.insertAfter($el.parents(".tree-container-header").first());

            $html.find("a.text-danger").click(function (evt) {
                evt.preventDefault();
                GecosUtils.askConfirmation({
                    callback: _.bind(that._deleteOU, ouId),
                    message: "Deleting an OU is a permanent action. It will also delete all its children."
                });
            });
        },

        hideContainerMenu: function () {
            App.tree.$el
                .find(".tree-extra-options").remove().end()
                .find(".extra-opts.fa-caret-down").removeClass("fa-caret-down")
                                                  .addClass("fa-caret-right");
        },

        highlightNodeById: function (id) {
            var $item = this.$el.find('#' + id);

            this.$el.find(".tree-selected").removeClass("tree-selected");
            if ($item.is(".tree-container")) {
                // It's a container
                $item.find(".tree-container-header").first().addClass("tree-selected");
            } else {
                $item.addClass("tree-selected");
            }
        },

        selectNode: function (evt) {
            evt.stopPropagation();
            var $el = $(evt.target),
                checked = $el.is(":checked"),
                $container = $el.parents(".tree-node").first();

            if ($container.is(".tree-container")) {
                $el = $container.find(".tree-container-header").first();
            } else {
                $el = $container;
            }

            if (checked) {
                $el.addClass("multiselected");
                this.selectionInfoView.addIdToSelection($container.attr("id"));
            } else {
                $el.removeClass("multiselected");
                this.selectionInfoView.removeIdFromSelection($container.attr("id"));
            }
        },

        clearNodeSelection: function () {
            this.$el.find("input.tree-selection").attr("checked", false);
            this.$el.find(".multiselected").removeClass("multiselected");
        }
    });
});
