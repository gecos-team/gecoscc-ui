/*jslint browser: true, nomen: true, unparam: true */
/*global App, TreeModel, gettext */

/*
* Copyright 2013, Junta de Andalucia
* http://www.juntadeandalucia.es/
*
* Authors:
*   Alberto Beiztegui <albertobeiz@gmail.com>
*   Alejandro Blanco <alejandro.b.e@gmail.com>
*
* All rights reserved - EUPL License V 1.1
* https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
*/

App.module("Tree", function (Tree, App, Backbone, Marionette, $, _) {
    "use strict";

    App.addInitializer(function () {
        var treeView,
            modelCut;

        App.instances.tree = new Tree.Models.TreeModel();
        App.instances.tree.reloadTree(function () {
            App.instances.treePromise.resolve(); // tree is loaded!
        });
        App.forestAuxiliary = "ForestAux";

        treeView = new Tree.Views.NavigationTree({
            model: App.instances.tree
        });
        App.tree.show(treeView);

        App.instances.tree.on("change", function () {
            treeView.activeNode = App.tree.currentView.activeNode;
            App.tree.show(treeView);
            _.each(App.instances.staging.toDelete, function (id) {
                $("#" + id).addClass("deleted");
                $("#" + id).removeClass("tree-selected");
            });
            _.each(App.instances.staging.toModify, function (id) {
                modelCut = $("#" + id).find(".tree-container-header").first();
                if (modelCut.length === 0) { modelCut = $("#" + id); }
                modelCut.addClass("modified");
                $("#" + id).removeClass("tree-selected");
            });
            _.each(App.instances.staging.toMove, function (ids) {
                modelCut = $("#" + ids[0]);
                modelCut.addClass("pasted");
                modelCut.removeClass("tree-selected");
                $("#" + ids[1]).find(".tree-container-content").first().prepend(modelCut);
            });
            if (App.instances.cut) {
                $("#" + App.instances.cut.get("id")).addClass("cut");
                $("#" + App.instances.cut.get("id")).removeClass("tree-selected");
            }
        });
    });
});

App.module("Tree.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.Node = Backbone.Model.extend({
        defaults: {
            id: -1,
            name: gettext("Loading nodes..."),
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

        // There must be only one pagination running!
        in_pagination: false,
        currentLoadedPage: 1,

        goToPage: function(page, params){
            if (this.in_pagination) {
                //console.log("Error, previous pagination in course!");
                if (!_.isUndefined(params) && !_.isUndefined(params.error)) {
                    params.error();
                }                
                
                return;
            }
            
            this.in_pagination = true;
            var that = this;
            
            var paginationOk = function() {
                //console.log("success!");
                that.in_pagination = false;
                that.currentLoadedPage = page;
                if (!_.isUndefined(params) && !_.isUndefined(params.success)) {
                    params.success();
                }
            }
            
            var paginationError = function() {
                //console.log("error!");
                that.in_pagination = false;
                if (!_.isUndefined(params) && !_.isUndefined(params.error)) {
                    params.error();
                }
            }            
            
            this.goTo(page, {
                success: paginationOk,
                error: paginationError
            });
        },
        
        paginator_core: {
            type: "GET",
            dataType: "json",
            url: function () {
                // maxdepth must be zero for pagination to work because in the
                // answer from the server there is no information about the
                // number of children in a container (OU)
                return "/api/nodes/?maxdepth=0&path=" + this.path +
                    ((this.search_filter.length > 0)?"&type=" + this.search_filter:'');
            },
            statusCode: {
                403: function() {
                    forbidden_access();
                }
            }
        },

        paginator_ui: {
            firstPage: 1,
            currentPage: 1,
            perPage: nav_tree_pagesize,
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
            if (!_.isString(options.search_filter)) {
                throw "Container collections require a search_filter attribute";
            }
            this.path = options.path;
            this.search_filter = options.search_filter;
        },

        parse: function (response) {
            this.totalPages = response.pages;
            return response.nodes;
        }
    });

    Models.Search = Models.Container.extend({
        initialize: function (options) {
            if (!_.isString(options.keyword)) {
                throw "Search collections require a keyword attribute";
            }
            if (!_.isString(options.search_by)) {
                throw "Search collections require a 'search by' attribute";
            }
            if (!_.isString(options.search_filter)) {
                throw "Search collections require a 'search filter' attribute";
            }
            this.keyword = options.keyword;
            this.search_by = options.search_by;
            this.search_filter = options.search_filter;
        },

        paginator_core: {
            type: "GET",
            dataType: "json",
            url: function () {
                return "/api/nodes/?iname=" + this.keyword + "&search_by=" + this.search_by+"&type="+this.search_filter;
            },
            statusCode: {
                403: function() {
                    forbidden_access();
                }
            }			
        }
    });

    Models.TreeModel = Backbone.Model.extend({
        parser: new TreeModel(),

        defaults: {
            tree: null,
            search_filter: [],
        },

        initialize: function (options) {
            var that = this,
                parent;
            this.search_filter = [];
            this.listenTo(App, 'action_change', function (result) {
                that.updateNodeById(result.objectId);
            });
            this.listenTo(App, 'action_delete', function (result) {
                parent = _.last(result.path.split(','));
                parent = App.instances.tree.findNodeById(parent);
                if (_.isUndefined(parent) || _.isUndefined(parent.paginatedChildren)) {
                    return;
                }
                App.instances.tree.loadFromPath(
                    result.path,
                    App.tree.currentView.activeNode
                );
            });
        },
        getUrl: function (options) {
            var params =  ["pagesize=99999"];
            if (_.has(options, "path")) { params.push("path=" + options.path); }
            if (this.search_filter.length > 0) { params.push("type=" + this.search_filter); }
            if (_.has(options, "oids")) {
                params.push("oids=" + options.oids);
            } else {
                // maxdepth messes with oids-filtered petitions
                params.push("maxdepth=0");
            }
            return "/api/nodes/?" + params.join('&');
        },

        reloadTree: function (callback) {
            var that = this;
            return $.ajax(this.getUrl({ path: "root" }), {
                success: function (response) {
                    var aux = that.parseNodesJSON(response.nodes),
                        root = aux[0];
                    if (root.children.length === 1) {
                        root.children[0].model.closed = false;
                    }
                    $.when.apply(that, aux[1]).done(function () {
                        that.set("tree", aux[0]);
                        if (callback) { callback(); }
                    });
                },
                error: function(xhr, textStatus, error){
                    if (xhr.status === 403) {
                        forbidden_access();
                    }
                    else {
                        console.log('Error: '+xhr.status+' '+xhr.statusText+' - '+textStatus+" - "+error);
                    }
                }
            });
        },

        _addPaginatedChildrenToModel: function (node) {
            var promise = $.Deferred(),
                path = node.path + ',' + node.id;

            var search_filter = App.instances.tree.getSearchFilter();
                
            node.paginatedChildren = new Models.Container({ path: path, search_filter: search_filter.join() });
            node.paginatedChildren.goToPage(1, {
                success: function () { promise.resolve(); },
                error: function () { promise.reject(); }
            });
            return promise;
        },

        parseNodesJSON: function (data) {
            var dataFiltered, nodes, rootId, rootPath, tree, promises, that;

            // Filter child nodes with parents already in the tree
            dataFiltered = _.filter(data, function (child) {
                return !_.some(child.path.split(","), function (parentId) {
                    return _.some(data, function (child2) {
                        return child2._id === parentId;
                    });
                });
            });

            // Prepare the nodes to be part of the tree
            nodes = _.map(dataFiltered, function (n) {
                return {
                    id: n._id,
                    path: n.path.split(','),
                    type: n.type,
                    name: n.name,
                    children: []
                };
            });

            // Create the tree, with only an auxiliary root node
            try {
                rootId = _.last(nodes[0].path);
                rootPath = _.initial(nodes[0].path).join(',');
            } catch (error) {
                rootId = "root";
                rootPath = "";
            }
            tree = this.parser.parse({
                id: rootId,
                path: rootPath,
                type: "AUXILIARY2",
                name: "AUXILIARY3",
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

        parsePath: function (path) {
            var parsed = {
                string: path,
                array: path.split(',')
            };
            parsed.last = _.last(parsed.array);
            parsed.parentPath = _.initial(parsed.array);
            parsed.parentId = _.last(parsed.parentPath);
            return parsed;
        },

        getNodeModel: function (parentNode, oldNode, id) {
            var newNode;

            if (parentNode.model.status === "paginated") {
                newNode = parentNode.model.paginatedChildren.get(id);
                if (!_.isUndefined(newNode)) {
                    newNode = newNode.toJSON();
                }
            } else if (parentNode.model.id === "root" || parentNode.model.status === "meta-only") {
                newNode = _.clone(oldNode.model);
                delete newNode.children;
            }

            if (_.isUndefined(newNode)) {
                // Parent unknown
                newNode = {
                    id: id,
                    type: "ou",
                    name: App.forestAuxiliary,
                    children: [],
                    closed: false,
                    status: "unknown"
                };
            }

            return newNode;
        },

        _getNodesToLoad: function (path, unknownIds) {
            var nodes = {};

            // Get the parent node of this node
            nodes.parentNode = this.getTreeNode(path.parentId) || this.get("tree");
            
            // Get this node from parent node children
            nodes.oldNode = _.find(nodes.parentNode.children, function (n) {
                return n.model.id === path.last;
            });

            // Get new node model
            nodes.newNode = this.getNodeModel(nodes.parentNode, nodes.oldNode, path.last);
            if (nodes.newNode.status === "unknown") {
                unknownIds.push(path.last);
                nodes.newNode.path = path.parentPath.join(',');
            }

            return nodes;
        },

        getSearchFilter: function() {
            var search_filter = ['ou'];
            $("input:checkbox[name=filter_type]:checked").each(function ()
            {
                search_filter.push($(this).val());
            });   
            return search_filter;
        },
        
        loadFromPath: function (path, childToShow, silent, search_filter) {
            var that, nodes, promises, unknownIds;
            //console.log("loadFromPath('"+path+"', '"+childToShow+"'");

            if (typeof search_filter !== 'undefined') {
                this.search_filter = search_filter;
            }
            else {
                var search_filter = this.getSearchFilter();
            }

            if (path === "root") { return [this.reloadTree()]; }

            that = this;
            path = this.parsePath(path);
            unknownIds = this.makePath(path.parentPath);
            nodes = this._getNodesToLoad(path, unknownIds);

            if (nodes.newNode.status === "unknown" 
                && nodes.parentNode.model.status === "unknown") {
                // Both this node and its parent are "unknown", probably 
                // the user can't view the parentNode because of lacking permissions.
                
                var newNode = this.findNodeById(nodes.newNode.id);
                if (!_.isUndefined(newNode)) {
                    nodes.newNode = newNode;
                }
            }
            
            nodes.newNode.status = "paginated";
            promises = [this._addPaginatedChildrenToModel(nodes.newNode)];
            
            // Reload all nodes of this path up to the root
            for (var i = 2; i<path.parentPath.length; i++) {
                // Check if the node is visible in nav-tree
                if ($("#" + path.parentPath[i]).length > 0) {
                    var ppath = this.findNodeById(path.parentPath[i]);  
                    promises.push(this._addPaginatedChildrenToModel(ppath));
                }
            }
            
            nodes.newNode = this.parser.parse(nodes.newNode);
            if (!_.isUndefined(nodes.oldNode)) {
                nodes.oldNode.drop();
            }
            nodes.parentNode.addChild(nodes.newNode);
            promises.push(this.resolveUnknownNodes(unknownIds, true));

            var completePath = nodes.newNode.model.path.split(",");
            var rootId = completePath[1];
            var root = this.findNodeById(rootId);                
            
            
            if (!_.isUndefined(childToShow) && childToShow!=null) {
                // Check if the child to show is an OU and must be reloaded
                var cts = this.findNodeById(childToShow);
                if (!_.isUndefined(cts) && cts.type == 'ou' 
                    && App.tree.currentView.isNodeOpen(childToShow)) {
                    promises.push(this._addPaginatedChildrenToModel(cts));
                }                
                
                // Open the correct page to show the child
                promises[0].done(function () {

                    var  domainPath;
                    that.searchPageForNode(
                        nodes.newNode.model.paginatedChildren,
                        childToShow,
                        false
                    );

                    if (completePath.length > 1 && !_.isUndefined(root)) {
                        domainPath = completePath[2] || nodes.newNode.model.id;
                        that.searchPageForNode(
                            root.paginatedChildren,
                            domainPath,
                            false
                        );
                    }
                });
            }
            else {
                // Restore last saved page for root node
                var page = App.tree.currentView.getCurrentPageforNode(rootId);
                if (jQuery.type(page) != "undefined" && root.paginatedChildren.currentPage != page) {
                    //console.log( "GOTO page: "+page );
                    root.paginatedChildren.goToPage(page, {
                        success: function () { that.trigger("change"); }
                    }); 
                }
            }

            this.openPath(path.array);
            if (!silent) {
                $.when.apply($, promises).done(function () {
                    that.trigger("change");
                });
            }

            return promises;
        },

        openPath: function (path) {
            var that = this;
            if (typeof path === "string") {
                path = path.split(",");
            }
            _.each(path, function (node) {
                node = that.findNodeById(node);
                if (!_.isUndefined(node)) {
                    that.openAllContainersFrom(node.id);
                }
            });
        },

        makePath: function (path) {
            var currentNode = this.get("tree"),
                tree = currentNode,
                unknownIds = [],
                pathAsArray = path,
                that = this;

            if (_.isString(path)) { pathAsArray = path.split(','); }
            path = "root";
            _.each(pathAsArray, function (step) {
                if (step === "root") { return; }

                var node = tree.first({ strategy: "breadth" }, function (n) {
                        return n.model.id === step;
                    });

                if (_.isUndefined(node)) {

                    node = {
                        id: step,
                        path: path,
                        type: "ou",
                        name: App.forestAuxiliary,
                        children: [],
                        closed: false,
                        status: "unknown"
                    };
                    node = that.parser.parse(node);
                    unknownIds.push(step);
                    currentNode.addChild(node);
                }
                path += ',' + step;
                currentNode = node;
            });

            return unknownIds;
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
                    if (!_.isUndefined(node)) {
                        node.model.name = n.name;
                        if (node.model.status !== "paginated") {
                            node.model.status = "meta-only";
                        }
                    }
                });
                if (!silent) { that.trigger("change"); }
            }).fail( function( jqXHR, textStatus, errorThrown ) {
                  if (jqXHR.status === 403) {
                    forbidden_access();
                  }
                  else {
                    console.log('Error: '+jqXHR.status+' '+jqXHR.statusText+' - '+textStatus+' - '+errorThrown);
                  }
            });
        },

        searchPageForNode: function (paginatedCollection, nodeId, silent) {
            if (_.isUndefined(paginatedCollection)) { return; }
            var that = this,
                search;

            search = function () {
                var node = paginatedCollection.get(nodeId),
                    page = paginatedCollection.currentLoadedPage + 1;
                if (_.isUndefined(node) && page <= paginatedCollection.totalPages) {
                    //console.log("GOTO: "+page+" NODE:"+nodeId);
                    paginatedCollection.goToPage(page, {
                        success: function () { search(); }
                    });
                } else if (!silent && !_.isUndefined(node)) {
                    that.trigger("change");
                }

            };

            search();
        },


        getTreeNode: function (id) {
            return this.get("tree").first({ strategy: 'breadth' }, function (n) {
                    return n.model.id === id;
                });
        },

        openAllContainersFrom: function (id, silent) {
            // Id must reference a container (OU)
            var node = this.getTreeNode(id);
            var paginatedChildren, openedAtLeastOne;

            if (!node) {
                console.warn("OU: "+id+" not found!");
                return; 
            }

            // Include the id passed
            openedAtLeastOne = node.model.closed;
            node.model.closed = false;
            // All the ancestors
            while (node.parent) {
                // Open the container
                openedAtLeastOne = openedAtLeastOne || node.parent.model.closed;
                node.parent.model.closed = false;

                // Show the right page
                if (node.parent.model.status === "paginated") {
                    paginatedChildren = node.parent.model.paginatedChildren;
                    this.searchPageForNode(paginatedChildren, node.model.id);
                }

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

                if (_.has(node.model, "paginatedChildren")) {
                    node.model.paginatedChildren.each(function (n) {
                        if (_.contains(ids, n.get("id"))) {
                            nodes.push(n.toJSON());
                        }
                    });
                }

                if (ids.length === nodes.length) {
                    return false;
                }
            });

            return nodes;
        },

        updateNodeById: function (id, silent) {
            // It's safe to assume in this case that the node is already
            // present in the tree (as container node or as child)
            var tree = this.get("tree"),
                node = this.getTreeNode(id),
                that = this;

            if (!_.isUndefined(node)) {
                node.model.name = "<span class='fa fa-spin fa-spinner'></span> " +
                    gettext("Loading");
                if (!silent) { this.trigger("change"); }
            }

            // Load the node new information
            $.ajax(this.getUrl({ oids: id })).done(function (response) {
                var data = response.nodes[0];

                node = that.getTreeNode(id);
                if (_.isUndefined(node)) {
                    // Maybe the node is not in the loaded page
                    return;
                }
                if (node.model.id !== id && _.has(node.model, "paginatedChildren")) {
                    node = node.model.paginatedChildren.get(id);
                }
                if (_.has(node, "set")) {
                    node.set("name", data.name);
                } else if (_.has(node.model, "name")) {
                    node.model.name = data.name;
                }

                if (!silent) { that.trigger("change"); }
            }).fail( function( jqXHR, textStatus, errorThrown ) {
                  if (jqXHR.status === 403) {
                    forbidden_access();
                  }
                  else {
                    console.log('Error: '+jqXHR.status+' '+jqXHR.statusText+' - '+textStatus+' - '+errorThrown);
                  }
            });
        },

        toJSON: function () {
            var tree = this.get("tree"),
                children;

            if (tree) {
                children = _.clone(tree.model.children);

                children = _.sortBy(children, function (child) {
                    return child.name;
                });
                children = _.sortBy(children, function (child) {
                    return child.path.length;
                });

                return children;
            }
            return {};
        },

        findNodeById: function (id) {
            var tree = this.get("tree"),
                node = tree.first(function (n) {
                    return n.model.id === id;
                });

            if (node) { return node.model; }

            // Node wasn't a loaded container, let's look in the paginated
            // children collections
            tree.walk(function (n) {
                if (n.model.status === "paginated") {
                    node = n.model.paginatedChildren.get(id);
                }
                if (node) {
                    return false;
                }
            });

            return node;
        }
    });
});
