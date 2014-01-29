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
            '<div class="tree-folder" style="display: block;" id="<%= id %>">\n' +
            '    <div class="tree-folder-header">\n' +
            '        <span class="opener fa fa-<%= controlIcon %>-square-o"></span> ' +
            '<span class="fa fa-group"></span>\n' +
            '        <div class="tree-folder-name"><%= name %> ' +
            '<span class="extra-opts fa fa-caret-right"></span></div>' +
            '<input type="checkbox" class="pull-right tree-selection">\n' +
            '    </div>\n' +
            '    <div class="tree-folder-content" ' +
            '<% if (closed) { print(\'style="display: none;"\'); } %>>\n',
        treeContainerPost =
            '    </div>\n' +
            '</div>\n',
        treeItem =
            '<div class="tree-item" style="display: block;" id="<%= id %>">\n' +
            '    <span class="fa fa-<%= icon %>"></span>\n' +
            '    <div class="tree-item-name"><%= name %></div>\n' +
            '    <input type="checkbox" class="pull-right tree-selection">\n' +
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

    Views.NavigationTree = Marionette.ItemView.extend({
        templates: {
            containerPre: _.template(treeContainerPre),
            containerPost: _.template(treeContainerPost),
            item: _.template(treeItem),
            emptyTree: _.template(emptyTree),
            extraOpts: _.template(extraOpts)
        },

        iconClasses: {
            user: "user",
            computer: "desktop",
            printer: "print",
            group: "link",
            storage: "hdd-o"
        },

        selectionInfoView: undefined,
        activeNode: null,

        events: {
            "click .tree-folder-header": "editNode",
            "click .tree-item": "editNode",
            "click .tree-folder-header .opener": "openContainer",
            "click .tree-folder-name .extra-opts": "showContainerMenu",
            "click .tree-folder-header .tree-selection": "selectNode",
            "click .tree-item .tree-selection": "selectNode"
        },

        initialize: function () {
            this.selectionInfoView = new Views.SelectionInfo({
                el: $("#tree-selection-info")[0]
            });
        },

        _loader: function (size) {
            size = size || 1;
            return "<p style='font-size: " + size + "em;'><span class='fa " +
                "fa-spinner fa-spin'></span> " + gettext("Loading") +
                "...</p>";
        },

        render: function () {
            var tree = this.model.toJSON(),
                oids = this.selectionInfoView.getSelection(),
                that = this,
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
            _.each(oids, function (id) {
                var $checkbox = that.$el.find('#' + id).find("input.tree-selection").first();
                $checkbox.attr("checked", true);
                $checkbox.parent().addClass("multiselected");
            });

            if (!_.isNull(this.activeNode)) {
                this.highlightNodeById(this.activeNode);
            }

            this.bindUIElements();
            return this;
        },

        recursiveRender: function (node) {
            var that = this,
                json = _.pick(node, "name", "type", "id", "closed"),
                html;

            if (json.type === "ou") {
                if (node.children.length === 0) {
                    json.closed = true;
                }
                json.controlIcon = json.closed ? "plus" : "minus";
                html = this.templates.containerPre(json);
                _.each(node.children, function (child) {
                    html += that.recursiveRender(child);
                });
                html += this.templates.containerPost(json);
            } else {
                json.icon = this.iconClasses[json.type];
                html = this.templates.item(json);
            }

            return html;
        },

        editNode: function (evt) {
            var $el = $(evt.target),
                that = this,
                node,
                parentId;

            this.hideContainerMenu();

            if ($el.is(".tree-folder-header") || $el.parent().is(".tree-folder-header")) {
                // It's an OU
                $el = $el.parents(".tree-folder").first();
            } else if (!$el.is(".tree-item")) {
                // It's a leaf
                $el = $el.parents(".tree-item").first();
            }
            this.activeNode = $el.attr("id");
            this.highlightNodeById(this.activeNode);

            parentId = $el.parents(".tree-folder").first().attr("id");
            if (_.isUndefined(parentId)) { parentId = "root"; }

            node = this.model.get("tree").first({ strategy: 'breadth' }, function (n) {
                return n.model.id === that.activeNode;
            });
            if (node) {
                App.instances.router.navigate("ou/" + parentId + "/" + node.model.type + "/" + this.activeNode, {
                    trigger: true
                });
            }
        },

        _openContainerAux: function ($el, $content, opened) {
            var node = this.model.get("tree"),
                id = $el.attr("id");
            node = node.first(function (obj) {
                return obj.model.id === id;
            });
            node.model.closed = !opened;
            if (opened && !(node.model.loaded && node.children.length > 0)) {
                $content.html(this._loader());
                this.model.loadFromNode(node.model.path, node.model.id);
            }
        },

        openContainer: function (evt) {
            evt.stopPropagation();
            var $el = $(evt.target).parents(".tree-folder").first(),
                $treeFolderContent = $el.find('.tree-folder-content').first(),
                classToTarget = '.fa-minus-square-o',
                classToAdd = 'fa-plus-square-o';

            this.hideContainerMenu();
            if ($el.find('.tree-folder-header').first().find('.fa-minus-square-o').length > 0) {
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
                ouId = $el.parents(".tree-folder").first().attr("id"),
                $html = $(this.templates.extraOpts({ ouId: ouId })),
                closing = $el.is(".fa-caret-down"),
                that = this;

            this.hideContainerMenu();
            if (closing) { return; }
            $el.removeClass("fa-caret-right").addClass("fa-caret-down");
            $html.insertAfter($el.parents(".tree-folder-header").first());

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
            if ($item.is(".tree-folder")) {
                // Is a container
                $item.find(".tree-folder-header").first().addClass("tree-selected");
            } else {
                $item.addClass("tree-selected");
            }
        },

        selectNode: function (evt) {
            evt.stopPropagation();
            var $el = $(evt.target),
                checked = $el.is(":checked");

            $el = $el.parent();
            if (checked) {
                $el.addClass("multiselected");
            } else {
                $el.removeClass("multiselected");
            }

            if ($el.is(".tree-folder-header")) {
                $el = $el.parent();
            }
            if (checked) {
                this.selectionInfoView.addIdToSelection($el.attr("id"));
            } else {
                this.selectionInfoView.removeIdFromSelection($el.attr("id"));
            }
        },

        clearNodeSelection: function () {
            this.$el.find("input.tree-selection").attr("checked", false);
            this.$el.find(".multiselected").removeClass("multiselected");
        }
    });

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
            this.$el.find("select").chosen();
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
});
