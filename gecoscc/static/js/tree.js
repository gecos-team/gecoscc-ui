/*jslint browser: true, nomen: true, unparam: true */
/*global $, App, TreeModel, GecosUtils, gettext */

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

App.module("Tree", function (Tree, App, Backbone, Marionette, $, _) {
    "use strict";

    App.addInitializer(function () {
        var treeView;

        App.instances.tree = new Tree.Models.TreeModel();
        App.instances.tree.reloadTree();

        treeView = new Tree.Views.NavigationTree({
            model: App.instances.tree
        });
        App.tree.show(treeView);

        App.instances.tree.on("change", function () {
            App.tree.show(treeView);
        });
    });
});

App.module("Tree.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.TreeModel = Backbone.Model.extend({
        parser: new TreeModel(),

        defaults: {
            tree: null
        },

        initTree: function (data) {
            var preprocessed = {
                    path: "root",
                    children: []
                },
                parsed;

            parsed = this.parseTree(preprocessed, data.nodes);
            _.each(parsed.children, function (n) {
                if (n.model.type === "ou") {
                    n.model.closed = false; // Open top level containers
                }
            });
            this.set("tree", parsed);
        },

        reloadTree: function () {
            var that = this;
            $.ajax("/api/nodes/?maxdepth=1", {
                success: function (response) {
                    that.initTree(response);
                }
            });
        },

        parseTree: function (root, data) {
            _.each(data, function (node) {
                var newNode = _.clone(node),
                    path = node.path.split(','),
                    aux;

                newNode.id = newNode._id;
                delete newNode._id;
                newNode.loaded = true;
                if (newNode.type === "ou") {
                    newNode.closed = true; // All container nodes start closed
                }

                aux = root.children;
                _.each(path, function (step) {
                    if (root.path.indexOf(step) >= 0) { return; }
                    var obj = _.find(aux, function (child) {
                        return child.id === step;
                    });
                    if (!obj) {
                        // This path step is not present, lets create the
                        // container
                        obj = {
                            id: step,
                            type: "ou",
                            name: "unknown",
                            loaded: false,
                            closed: true, // All container nodes start closed
                            children: []
                        };
                        aux.push(obj);
                    }
                    aux = obj.children;
                });

                // We have arrived to the parent of the newNode (aux),
                // newNode may be already present if it was created as a
                // container
                node = _.find(aux, function (obj) {
                    return obj.id === newNode.id;
                });
                if (node) {
                    _.defaults(node, newNode);
                } else {
                    newNode.children = [];
                    aux.push(newNode);
                }
            });

            return this.parser.parse(root);
        },

        toJSON: function () {
            var tree = this.get("tree");
            if (tree) {
                return _.clone(tree.model.children[0]);
            }
            return {};
        },

        loadFromNode: function (nodePath, nodeId, loadHimself) {
            var url = "/api/nodes/?maxdepth=1&path=" + nodePath,
                that = this;

            if (!loadHimself) { url += ',' + nodeId; }
            return $.ajax(url, {
                success: function (response) {
                    var treeModel = new Models.TreeModel();
                    treeModel.initTree(response);
                    that.addTree(treeModel.get("tree"));
                }
            });
        },

        addNode: function (referenceID, obj) {
            var tree = this.get("tree"),
                parent,
                node;
            node = this.parser.parse(obj);
            parent = tree.first(function (n) {
                return n.model.id === referenceID;
            });
            parent.addChild(node);
            this.trigger("change");
        },

        addTree: function (root) {
            var tree = this.get("tree"),
                that = this,
                findNode;

            findNode = function (root, id) {
                return root.first({ strategy: 'breadth' }, function (node) {
                    return node.model.id === id;
                });
            };

            root.walk({ strategy: 'breadth' }, function (node) {
                if (node.model.path === 'root') { return; }

                var reference = findNode(tree, node.model.id),
                    model = _.clone(node.model),
                    newNode,
                    parent;

                delete model.children;

                if (reference && !reference.model.loaded && node.model.loaded) {
                    // The node already exists, load the data in it
                    model.children = reference.model.children;
                    model.closed = reference.model.closed;
                    parent = reference.parent;
                    reference.drop();
                    newNode = that.parser.parse(model);
                    parent.addChild(newNode);
                } else if (!reference) {
                    // We need to add a new node, let's find the parent
                    reference = findNode(tree, node.parent.model.id);
                    if (reference) { // This should always eval to true
                        model.children = [];
                        newNode = that.parser.parse(model);
                        reference.addChild(newNode);
                    }
                }
            });

            this.trigger("change");
        },

        openAllContainersFrom: function (id) {
            var node = this.get("tree").first(function (n) {
                    return n.model.id === id;
                });

            if (!node) { return; }
            while (node.parent) {
                node.parent.model.closed = false;
                node = node.parent;
            }
        }
    });
});

App.module("Tree.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    var treeContainerPre =
            '<div class="tree-folder" style="display: block;" id="<%= id %>">\n' +
            '    <div class="tree-folder-header">\n' +
            '        <span class="opener fa fa-<%= controlIcon %>-square-o"></span> ' +
            '<span class="fa fa-group"></span>\n' +
            '        <div class="tree-folder-name"><%= name %> ' +
            '<span class="extra-opts fa fa-caret-right"></span></div>\n' +
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
            '</div>\n',
        extraOpts =
            '<div class="tree-extra-options">\n' +
            '    <ul class="nav nav-pills nav-stacked">\n' +
            '        <li><a href="#ou/<%= ouId %>/new">\n' +
            '            <span class="fa fa-plus"></span> ' + gettext('Add new') + '\n' +
            '        </a></li>\n' +
            '        <li><a href="#" class="text-danger">\n' +
            '            <span class="fa fa-times"></span> ' + gettext('Borrar') + '\n' +
            '        </a></li>\n' +
            '    </ul>\n' +
            '</div>\n';

    Views.NavigationTree = Marionette.ItemView.extend({
        templates: {
            containerPre: _.template(treeContainerPre),
            containerPost: _.template(treeContainerPost),
            item: _.template(treeItem),
            extraOpts: _.template(extraOpts)
        },

        iconClasses: {
            user: "user",
            computer: "desktop",
            printer: "printer"
        },

        newItemModal: undefined,

        events: {
            "click .tree-folder-header": "selectContainer",
            "click .tree-folder-header .opener": "openContainer",
            "click .tree-folder-name .extra-opts": "containerExtraOptions",
            "click .tree-item": "selectItem"
        },

        render: function () {
            var tree = this.model.toJSON(),
                html;

            if (_.keys(tree).length > 0) {
                html = this.recursiveRender(tree);
            } else {
                html = this.loader(2.5);
            }

            this.$el.html(html);
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

        loader: function (size) {
            size = size || 1;
            return "<p style='font-size: " + size + "em;'><span class='fa " +
                "fa-spinner fa-spin'></span> " + gettext("Loading") +
                "...</p>";
        },

        selectContainer: function (evt) {
            var $el = $(evt.target),
                $container,
                parentId,
                id;

            if ($el.is(".opener") || $el.is(".extra-opts") || $el.is("button")) {
                return;
            }

            this.closeExtraOptions();
            $container = $el.parents(".tree-folder").first();
            id = $container.attr("id");
            parentId = $container.parents(".tree-folder").first().attr("id");

            this.$el.find(".tree-selected").removeClass("tree-selected");
            $container.find(".tree-folder-header").first().addClass("tree-selected");

            App.instances.router.navigate("ou/" + parentId + "/ou/" + id, {
                trigger: true
            });
        },

        openContainer: function (evt) {
            var $el = $(evt.target).parents(".tree-folder").first(),
                $treeFolderContent = $el.find('.tree-folder-content').first(),
                classToTarget,
                classToAdd;

            this.closeExtraOptions();
            if ($el.find('.tree-folder-header').first().find('.fa-minus-square-o').length > 0) {
                classToTarget = '.fa-minus-square-o';
                classToAdd = 'fa-plus-square-o';
                $treeFolderContent.hide();
            } else {
                classToTarget = '.fa-plus-square-o';
                classToAdd = 'fa-minus-square-o';
                this.openContainerAux($el, $treeFolderContent);
                $treeFolderContent.show();
            }

            $el.find(classToTarget).first()
                .removeClass('fa-plus-square-o fa-minus-square-o')
                .addClass(classToAdd);
        },

        openContainerAux: function ($el, $content) {
            var node = this.model.get("tree"),
                id = $el.attr("id");
            node = node.first(function (obj) {
                return obj.model.id === id;
            });
            node.model.closed = false;
            if (!(node.model.loaded && node.children.length > 0)) {
                $content.html(this.loader());
                this.model.loadFromNode(node.model.path, node.model.id);
            }
        },

        containerExtraOptions: function (evt) {
            evt.preventDefault();
            var $el = $(evt.target),
                ouId = $el.parents(".tree-folder").first().attr("id"),
                $html = $(this.templates.extraOpts({ ouId: ouId })),
                closing = $el.is(".fa-caret-down");

            this.closeExtraOptions();
            if (closing) { return; }
            $el.removeClass("fa-caret-right").addClass("fa-caret-down");
            $html.insertAfter($el.parents(".tree-folder-header").first());

            $html.find("a.text-danger").click(function (evt) {
                evt.preventDefault();
                GecosUtils.confirmModal.find("button.btn-danger")
                    .off("click")
                    .on("click", function (evt) {
                        evt.preventDefault();
                        var model = new App.OU.Models.OUModel({ id: ouId });
                        model.destroy({
                            success: function () {
                                App.instances.tree.reloadTree();
                            }
                        });
                        GecosUtils.confirmModal.modal("hide");
                    });
                GecosUtils.confirmModal.modal("show");
            });
        },

        closeExtraOptions: function () {
            App.tree.$el
                .find(".tree-extra-options").remove().end()
                .find(".extra-opts.fa-caret-down").removeClass("fa-caret-down").addClass("fa-caret-right");
        },

        selectItem: function (evt) {
            var $el = $(evt.target).parents(".tree-item").first(),
                containerId = $el.parents(".tree-folder").first().attr("id"),
                id = $el.attr("id"),
                item;

            this.closeExtraOptions();
            this.$el.find(".tree-selected").removeClass("tree-selected");
            $el.addClass("tree-selected");

            item = this.model.get("tree").first(function (node) {
                return node.model.id === id;
            });

            if (item && item.model.type === "user") {
                App.instances.router.navigate("ou/" + containerId + "/user/" + id, {
                    trigger: true
                });
            }
        },

        selectItemById: function (id) {
            var $item;

            this.model.openAllContainersFrom(id);
            this.render();

            $item = this.$el.find('#' + id);
            this.$el.find(".tree-selected").removeClass("tree-selected");
            if ($item.is(".tree-folder")) {
                // Is a container
                $item.find(".tree-folder-header").first().addClass("tree-selected");
            } else {
                $item.addClass("tree-selected");
            }
        }
    });
});
