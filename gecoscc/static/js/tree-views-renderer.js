/*jslint browser: true, nomen: true, unparam: true */
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

// Contains code from Fuel UX Tree - https://github.com/ExactTarget/fuelux
// Copyright (c) 2012 ExactTarget - Licensed under the MIT license

App.module("Tree.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";
    
    Views.iconClasses = {
        ou: "folder",
        user: "user",
        computer: "desktop",
        printer: "print",
        group: "group",
        storage: "hdd-o",
        repository: "archive"
    };

    var treeContainerPre =
            '<div class="tree-container tree-node" style="display: block;" id="<%= id %>" data-path="<%= path %>">\n' +
            '    <div class="tree-container-header">\n' +
            '        <div class="tree-highlight">\n' +
            '            <span class="opener fa fa-<%= controlIcon %>-square-o"></span><span class="fa fa-' + Views.iconClasses['ou'] + '"></span>\n' +
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

    Views.Renderer = function (options) {
        this.$el = options.$el;
        this.model = options.model;

        this._templates = {
            containerPre: _.template(treeContainerPre),
            containerPost: _.template(treeContainerPost),
            emptyContainer: _.template(emptyContainer),
            item: _.template(treeItem),
            pagItem: _.template(paginationItem),
            emptyTree: _.template(emptyTree),
            extraOpts: _.template(extraOpts)
        };

        this._loader = function (size) {
            size = size || 1;
            return "<p style='font-size: " + size + "em;'><span class='fa " +
                "fa-spinner fa-spin'></span> " + gettext("Loading") +
                "...</p>";
        };

        this.render = function (view) {
            var tree = this.model.toJSON(),
                html;

            if (_.isUndefined(tree)) {
                // Empty tree
                html = this._templates.emptyTree({});
            } else if (_.keys(tree).length > 0) {
                html = this.recursiveRender(tree);
            } else {
                html = this._loader(2.5);
            }
            this.$el.html(html);
            this.renderSelection(view);
            if (!_.isNull(view.activeNode)) {
                view.highlightNodeById(view.activeNode);
            }

            return this;
        };

        this.renderSelection = function (view) {
            var oids = view.selectionInfoView.getSelection(),
                that = this;

            _.each(oids, function (id) {
                var $checkbox = that.$el.find('#' + id).find("input.tree-selection").first();
                $checkbox.attr("checked", true);
                $checkbox.parent().parent().addClass("multiselected");
            });
        };

        this.recursiveRender = function (node, root) {
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
                html = this._templates.item(json);
            }

            return html;
        };

        this.prepareRenderOUData = function (treeNode) {
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
                data.showPrev = paginatedChildren.currentPage > 1;
                data.showNext = paginatedChildren.currentPage < paginatedChildren.totalPages;
            } else if (treeNode.model.status === "meta-only") {
                data.children = _.map(treeNode.children, function (child) {
                    return child.model;
                });
                data.showNext = true;
            } else {
                throw "The node has the invalid status: " + treeNode.model.status;
            }

            return data;
        };

        this.renderOU = function (json, data, treeNode) {
            var html = this._templates.containerPre(json),
                that = this;

            if (data.children.length > 0) {
                if (data.showPrev) {
                    html += this._templates.pagItem({ type: "up" });
                }
                _.each(data.children, function (child) {
                    html += that.recursiveRender(child, treeNode);
                });
                if (data.showNext) {
                    html += this._templates.pagItem({ type: "down" });
                }
            } else {
                html += this._templates.emptyContainer(json);
            }

            return html + this._templates.containerPost(json);
        };
    };
});
