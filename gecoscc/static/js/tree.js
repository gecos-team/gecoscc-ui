/*jslint browser: true, nomen: true, unparam: true */
/*global $, App, TreeModel */

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
        App.instances.tree = new Tree.Models.TreeModel();
        $.ajax("/api/nodes/?maxdepth=1", {
            success: function (response) {
                App.instances.tree.initTree(response);
            }
        });
        var treeView = new Tree.Views.NavigationTree({
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

        parseTree: function (root, data) {
            _.each(data, function (node) {
                var newnode = _.clone(node),
                    path = node.path.split(','),
                    aux;

                newnode.id = newnode._id;
                delete newnode._id;
                newnode.loaded = true;
                if (newnode.type === "ou") {
                    newnode.closed = true; // All container nodes start closed
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

                // We have arrived to the parent of the newnode (aux),
                // newnode may be already present if it was created as a
                // container
                node = _.find(aux, function (obj) {
                    return obj.id === newnode.id;
                });
                if (node) {
                    _.defaults(node, newnode);
                } else {
                    newnode.children = [];
                    aux.push(newnode);
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

        loadFromNode: function (node) {
            var url = "/api/nodes/?maxdepth=1&path=",
                that = this;
            url += node.model.path + "," + node.model.id;
            $.ajax(url, {
                success: function (response) {
                    var root = _.pick(node.parent.model, "id", "name", "type"),
                        newnode;

                    // Prepare the parsing operation, need to provide an
                    // adecuate root where put the new nodes
                    root.path = node.model.path;
                    root.children = [];
                    newnode = that.parseTree(root, response.nodes);
                    // Look for our reference node
                    newnode = newnode.first(function (n) {
                        return n.model.id === node.model.id;
                    });

                    if (newnode.children) {
                        // Add the children to the tree, they are the new data
                        _.each(newnode.children, function (n) {
                            node.addChild(n);
                        });
                    }
                    // else empty!

                    that.trigger("change");
                }
            });
        }
    });
});

App.module("Tree.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    var treeContainerPre =
            '<div class="tree-folder" style="display: block;" id="<%= id %>">\n' +
            '    <div class="tree-folder-header">\n' +
            '        <span class="fa fa-<%= controlIcon %>-square-o"></span> ' +
            '        <span class="fa fa-group"></span>\n' +
            '        <div class="tree-folder-name"><%= name %></div>\n' +
            '    </div>\n' +
            '    <div class="tree-folder-content" ' +
            '<% if (closed) { print(\'style="display: none;"\'); } %>>\n',
        treeContainerPost =
            '    </div>\n' +
            '</div>',
        treeItem =
            '<div class="tree-item" style="display: block;" id="<%= id %>">' +
            '    <span class="fa fa-<%= icon %>"></span>' +
            '    <div class="tree-item-name"><%= name %></div>' +
            '</div>';

    Views.NavigationTree = Marionette.ItemView.extend({
        templates: {
            containerPre: _.template(treeContainerPre),
            containerPost: _.template(treeContainerPost),
            item: _.template(treeItem)
        },

        iconClasses: {
            user: "user",
            computer: "desktop",
            printer: "printer"
        },

        events: {
            "click .tree-folder-header": "selectContainer",
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
                if (!(node.loaded && node.children.length > 0)) {
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
                "fa-spinner fa-spin'></span> Loading...</p>";
        },

        selectContainer: function (evt) {
            var $el = $(evt.target).parents(".tree-folder").first(),
                $treeFolderContent = $el.find('.tree-folder-content').first(),
                classToTarget,
                classToAdd;

            if ($el.find('.tree-folder-header').first().find('.fa-minus-square-o').length > 0) {
                classToTarget = '.fa-minus-square-o';
                classToAdd = 'fa-plus-square-o';
                $treeFolderContent.hide();
            } else {
                classToTarget = '.fa-plus-square-o';
                classToAdd = 'fa-minus-square-o';
                this.openContainer($el, $treeFolderContent);
                $treeFolderContent.show();
            }

            $el.find(classToTarget).first()
                .removeClass('fa-plus-square-o fa-minus-square-o')
                .addClass(classToAdd);
        },

        openContainer: function ($el, $content) {
            var node = this.model.get("tree"),
                id = $el.attr("id");
            node = node.first(function (obj) {
                return obj.model.id === id;
            });
            node.model.closed = false;
            if (!(node.model.loaded && node.children.length > 0)) {
                $content.html(this.loader());
                this.model.loadFromNode(node);
            }
        },

        selectItem: function (evt) {
            var $el = $(evt.target).parents(".tree-item").first(),
                id = $el.attr("id"),
                item;

            this.$el.find(".tree-item").removeClass("tree-selected");
            $el.addClass("tree-selected");

            item = this.model.get("tree").first(function (node) {
                return node.model.id === id;
            });

            if (item && item.model.type === "user") {
                App.instances.router.navigate("user/" + id, { trigger: true });
            }
        }
    });
});
