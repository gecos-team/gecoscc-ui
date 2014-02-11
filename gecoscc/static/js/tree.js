/*jslint browser: true, nomen: true, unparam: true */
/*global App, TreeModel */

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

    Models.Node = Backbone.Model.extend({
        defaults: {
            type: "AUXILIARY",
            name: "AUXILIARY",
            status: "unknown"
        },

        parse: function (response) {
            response.id = response._id;
            delete response._id;
            response.status = "meta-only";
            return response;
        }
    });

    Models.Container = Backbone.Paginator.requestPager.extend({
        model: Models.Node,

        ajax: {
            maxdepth: 0, // It must be zero for pagination to work because
                         // in the answer there is no information about the
                         // number of children in a container (OU)
            pagesize: 3,
            path: "root"
        },

        paginator_core: {
            type: "GET",
            dataType: "json",
            url: function () {
                var params = [
                    "pagesize=" + this.ajax.pagesize,
                    "maxdepth=" + this.ajax.maxdepth,
                    "path=" + this.ajax.path
                ];
                return "/api/nodes/?" + params.join('&');
            }
        },

        paginator_ui: {
            firstPage: 0,
            currentPage: 0,
            perPage: 10,
            pagesInRange: 1,
            // 10 as a default in case your service doesn't return the total
            totalPages: 10
        },

        server_api: {
            page: function () { return this.currentPage; },
            pagesize: function () { return this.perPage; }
        },

        initialize: function (options) {
            if (!_.isString(options.path)) {
                throw "Container collections require a path attribute";
            }
            this.ajax.path = options.path;
        },

        parse: function (response) {
            this.totalPages = response.pages;
            return response.nodes;
        }
    });

    Models.TreeModel = Backbone.Model.extend({
        parser: new TreeModel(),

        defaults: {
            tree: null
        },

        ajaxDefaults: {
            maxdepth: 0, // It must be zero for pagination to work because
                         // in the answer there is no information about the
                         // number of children in a container (OU)
            pagesize: 3,
            page: 0 // Pagination starts in zero
        },

        getUrl: function (options) {
            var params;
            options = _.defaults(options, this.ajaxDefaults);
            params =  [
                "pagesize=" + options.pagesize,
                "maxdepth=" + options.maxdepth,
                "page=" + options.page
            ];
            if (_.has(options, "path")) { params.push("path=" + options.path); }
            if (_.has(options, "oids")) {
                // This case is special, pagination and depth must be avoided
                params = ["oids=" + options.oids, "pagesize=" + 99999];
            }
            return "/api/nodes/?" + params.join('&');
        },

        reloadTree: function () {
            var that = this;
            $.ajax(this.getUrl({ maxdepth: 1, pagesize: 99999, path: "root" }), {
                success: function (response) {
                    var aux = that.parseNodesJSON(response.nodes);
                    aux[0].children[0].model.closed = false;
                    $.when.apply(that, aux[1]).done(function () {
                        that.set("tree", aux[0]);
                    });
                }
            });
        },

        _addPaginatedChildrenToModel: function (node) {
            var promise = $.Deferred(),
                path = node.path + ',' + node._id;
            node.paginatedChildren = new Models.Container({ path: path });
            node.paginatedChildren.goTo(0, {
                success: function () { promise.resolve(); },
                error: function () { promise.reject(); }
            });
            return promise;
        },

        parseNodesJSON: function (data) {
            var nodes, rootId, tree, promises, that;

            // Prepare the nodes to be part of the tree
            nodes = _.map(data, function (n) {
                return {
                    id: n._id,
                    path: n.path.split(','),
                    type: n.type,
                    name: n.name,
                    children: []
                };
            });
            nodes = _.sortBy(nodes, function (n) {
                return n.path.length;
            });

            // Create the tree, with only an auxiliary root node
            rootId = _.last(nodes[0].path);
            tree = this.parser.parse({
                id: rootId,
                path: _.initial(nodes[0].path).join(','),
                type: "AUXILIARY",
                name: "AUXILIARY",
                children: [],
                closed: false,
                status: "unknown"
            });

            that = this;
            promises = [];
            _.each(nodes, function (n) {
                if (n.id === rootId || n.type !== "ou") { return; }
                // Add container nodes to the tree, since they are ordered by
                // path length the parent node should always be present in the
                // tree
                var parent, parentId;

                parentId = _.last(n.path);
                n.path = n.path.join(',');
                n.closed = true;
                n.status = "paginated";
                promises.push(that._addPaginatedChildrenToModel(n));
                n = that.parser.parse(n);

                parent = tree.first(function (n) {
                    return n.id === parentId;
                });
                if (_.isUndefined(parent)) { parent = tree; }
                parent.addChild(n);
            });

            return [tree, promises];
        },

        loadFromPath: function (path, page) {
            var url = this.getUrl({ path: path, page: page }),
                that = this;

            return $.ajax(url, {
                success: function (response) {
                    var aux = that.parseNodesJSON(response.nodes),
                        promises = that.addSubTree(aux[0], true);
                    aux[1].push(promises);
                    $.when.apply(that, _.flatten(aux[1])).done(function () {
                        that.trigger("change");
                    });
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

        makePath: function (pathAsString) {
            var path = pathAsString.split(','),
                currentNode = this.get("tree"),
                unknownIds = [];

            _.each(path, function (step) {
                if (step === "root") { return; }

                var node = currentNode.first({ strategy: "breadth" }, function (n) {
                        return n.model.id === step;
                    }),
                    that = this;

                if (_.isUndefined(node)) {
                    unknownIds.push(step);
                    node = {
                        id: step,
                        type: "ou",
                        name: "AUXILIARY",
                        children: [],
                        closed: false,
                        status: "unknown"
                    };
                    node = that.parser.parse(node);
                    currentNode.addChild(node);
                }
                currentNode = node;
            });

            return unknownIds;
        },

        addSubTree: function (subTree, silent) {
            var tree = this.get("tree"),
                unknownIds = this.makePath(subTree.model.path),
                promises = [],
                that = this,
                findNode;

            findNode = function (id) {
                return tree.first({ strategy: "breadth" }, function (node) {
                    return node.model.id === id;
                });
            };

            subTree.walk({ strategy: "breadth" }, function (node) {
                if (node.model.type === "AUXILIARY") { return; }

                var reference = findNode(node.model.id),
                    model = _.clone(node.model),
                    newNode,
                    parent;

                delete model.children;

                if (reference && reference.model.status === "unknown" && model.status !== "unknown") {
                    // The node already exists, load the data in it
                    model.children = reference.model.children;
                    model.closed = reference.model.closed;
                    parent = reference.parent;
                    reference.drop();
                    newNode = that.parser.parse(model);
                    parent.addChild(newNode);
                } else if (!reference || model.type === "ou") {
                    // We need to add a new container, let's find the parent
                    reference = findNode(node.parent.model.id);
                    if (reference) { // This should always eval to true
                        model.children = [];
                        model.status = "paginated";
                        promises.push(that._addPaginatedChildrenToModel(model));
                        newNode = that.parser.parse(model);
                        reference.addChild(newNode);
                    }
                }
            });

            promises.push(this.resolveUnknownNodes(unknownIds, silent));
            return promises;
        },

        resolveUnknownNodes: function (unknownIds, silent) {
            var that = this,
                promise,
                oids;

            if (unknownIds.length === 0) {
                promise = $.Deferred();
                promise.resolve();
                return promise;
            }

            oids = unknownIds.join(',');
            return $.ajax(this.getUrl({ oids: oids })).done(function (response) {
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

        openAllContainersFrom: function (id, silent) {
            var node = this.get("tree").first({ strategy: 'breadth' }, function (n) {
                    return n.model.id === id;
                }),
                openedAtLeastOne = false;

            if (!node) { return; }

            while (node.parent) {
                openedAtLeastOne = openedAtLeastOne || node.parent.model.closed;
                node.parent.model.closed = false;
                node = node.parent;
            }

            if (openedAtLeastOne && !silent) { this.trigger("change"); }
        },

        findNodes: function (ids) {
            var tree = this.get("tree"),
                nodes = [];

            tree.walk({ strategy: 'breadth' }, function (node) {
                if (_.contains(ids, node.model.id)) {
                    nodes.push(node.model);
                }
                // TODO look into paginated collections too?
                if (ids.length === nodes.length) {
                    return false;
                }
            });

            return nodes;
        },

        updateNodeById: function (id, silent) {
            // It's safe to assume in this case that the node is already
            // present in the tree

            // FIXME reload pageof the proper paginated collection
            // lookup parent, check if node in loaded page, reload then

            var tree = this.get("tree"),
                that = this,
                node = tree.first({ strategy: 'breadth' }, function (n) {
                    return n.model.id === id;
                });

            node.model.name = "<span class='fa fa-spin fa-spinner'></span> " + gettext("Loading");
            if (!silent) { this.trigger("change"); }
            $.ajax(this.getUrl({ oids: id })).done(function (response) {
                var data = response.nodes[0];
                node.model.name = data.name;
                node.model.type = data.type;
                if (!silent) { that.trigger("change"); }
            });
        },

        toJSON: function () {
            var tree = this.get("tree");
            if (tree) {
                // Everything must be contained in one OU
                return _.clone(tree.model.children[0]);
            }
            return {};
        }
    });
});
