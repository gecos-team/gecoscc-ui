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
                aux;

            aux = this.parseTree(preprocessed, data.nodes);
            _.each(aux[0].children, function (n) {
                if (n.model.type === "ou") {
                    n.model.closed = false; // Open top level containers
                }
            });
            this.set("tree", aux[0]);
            return aux[1]; // Return unknown ids
        },

        reloadTree: function () {
            var that = this;
            $.ajax("/api/nodes/?maxdepth=1", {
                success: function (response) {
                    var unknownIds = that.initTree(response);
                    that.resolveUnknownNodes(unknownIds);
                }
            });
        },

        parseTree: function (root, data) {
            var unknownIds = [];

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
                        unknownIds.push(step);
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

            return [this.parser.parse(root), unknownIds];
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
                    var treeModel = new Models.TreeModel(),
                        unknownIds = treeModel.initTree(response),
                        promise;

                    that.addTree(treeModel.get("tree"), true);
                    promise = that.resolveUnknownNodes(unknownIds, true);
                    if (_.isUndefined(promise)) {
                        promise = $.Deferred();
                        promise.resolve();
                    }
                    promise.done(function () { that.trigger("change"); });
                }
            });
        },

        addNode: function (referenceID, obj, silent) {
            var tree = this.get("tree"),
                parent,
                node;
            node = this.parser.parse(obj);
            parent = tree.first(function (n) {
                return n.model.id === referenceID;
            });
            parent.addChild(node);
            if (!silent) { this.trigger("change"); }
        },

        addTree: function (root, silent) {
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

            if (!silent) { this.trigger("change"); }
        },

        resolveUnknownNodes: function (unknownIds, silent) {
            var that = this,
                oids;

            if (unknownIds.length === 0) { return; }
            oids = unknownIds.join(',');

            return $.ajax("/api/nodes/?oids=" + oids).done(function (response) {
                var tree = that.get("tree");
                _.each(response.nodes, function (n) {
                    var node = tree.first(function (item) {
                        return item.model.id === n._id;
                    });
                    node.model.name = n.name;
                });
                if (!silent) { that.trigger("change"); }
            });
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
        },

        findNodes: function (ids) {
            var tree = this.get("tree"),
                nodes = [];

            tree.walk({strategy: 'breadth'}, function (node) {
                if (_.contains(ids, node.model.id)) {
                    nodes.push(node.model);
                }
                if (ids.length === nodes.length) {
                    return false;
                }
            });

            return nodes;
        }
    });
});
