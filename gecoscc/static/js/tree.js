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
                            name: gettext("unknown"),
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
                if (node && !node.loaded) {
                    _.extend(node, newNode);
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
