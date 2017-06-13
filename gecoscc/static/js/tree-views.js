/*jslint browser: true, nomen: true, unparam: true */
/*global App, gettext, GecosUtils */

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

// Contains code from Fuel UX Tree - https://github.com/ExactTarget/fuelux
// Copyright (c) 2012 ExactTarget - Licensed under the MIT license

App.module("Tree.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.NavigationTree = Marionette.ItemView.extend({
        rendered: undefined,
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
            this.renderer = new Views.Renderer({
                $el: this.$el,
                model: this.model
            });
            this.selectionInfoView = new Views.SelectionInfo({
                el: $("#tree-selection-info")[0]
            });
            $("#tree-search-btn")
                .off("click")
                .on("click", function (evt) {
                    evt.preventDefault();
                    var keyword = $("#tree-search").val().trim();
                    var search_by = $('input:radio[name=search_by]:checked').val();
                    var search_filter = App.instances.tree.getSearchFilter();

                    // If all the elements are selected do not filter
                    if (search_filter.length == 7) {
                        search_filter = []
                    }

                    //empty search reload tree
                    if (!keyword) {
                        App.instances.tree.loadFromPath("root", App.tree.currentView.activeNode, false, search_filter);
                    } else {
                        App.instances.router.navigate("search/" + keyword + "?searchby="+search_by+"&searchfilter="+search_filter,
                                                  { trigger: true });
                        $("#tree-close-search-btn").show();
                    }
                });
            //click button when enter key is pressed
            $("#tree-search").keyup(function (evt) {
                if (evt.which === 13) {
                    $("#tree-search-btn").click();
                }
            });
            
            $('#tree_search_drowpdown').on('hidden.bs.dropdown', function () {
                $("#tree-search-btn").click();
            });                 

            $("#tree-close-search-btn")
                .hide()
                .click(function (evt) {
                    evt.preventDefault();
                    App.instances.tree.loadFromPath("root");
                    $(this).hide();
                    $("#tree-search").val("");
                    App.instances.router.navigate("/", { trigger: false });
                });
        },

        render: function () {
            this.isClosed = false;
            this.triggerMethod("before:render", this);
            this.triggerMethod("item:before:render", this);

            this.renderer.render(this);

            this.bindUIElements();
            this.delegateEvents(this.events);
            this.triggerMethod("render", this);
            this.triggerMethod("item:rendered", this);

            return this;
        },

        stopPropagation: function (evt) {
            evt.stopPropagation();
        },
        
        editNode: function (evt) {
            var $el = $(evt.target).parents(".tree-node").first(),
                that = this,
                node,
                parentId;

            if ($el.attr("id") === "-1") {
                return;
            }

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
            var that, $el, prev, node, page, searchId, id, path;

            that = this;
            $el = $(evt.target);
            if (!$el.is(".tree-pagination")) {
                $el = $el.parents(".tree-pagination").first();
            }
            prev = $el.data("pagination") === "up";
            $el = $el.parents(".tree-container").first();
            id = $el.attr("id");
            path = $el.attr("data-path");
            node = this.model.get("tree").first(function (obj) {
                return obj.model.id === id;
            });

            if (node.model.status === "paginated") {
                page = node.model.paginatedChildren.currentPage;
                page = prev ? page - 1 : page + 1;
                if (page < 1) {
                    page = 1;
                }
                
                if (page > node.model.paginatedChildren.totalPages) {
                    page = node.model.paginatedChildren.totalPages;
                }
                
                // Only save current page for root node
                if ("root" == path) {
                    this.setCurrentPageforNode(id, page);
                }
                node.model.paginatedChildren.goToPage(page, {
                    success: function () { that.model.trigger("change"); }
                });
            } else {
                searchId = $el.find(".tree-container").first().attr("id");
                if ("root" == path) {
                    this.setCurrentPageforNode(id, 0);
                }
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
                $content.html(this.renderer._loader());
                this.model.loadFromPath(path + ',' + id);
            }
        },

        openContainerForNodeId: function (nodeId) {
            var elem = $('#'+nodeId);
            var content = elem.find(".tree-container-content").first();
            var header = elem.find(".tree-container-header").first();
            var icon = header.find(".fa-plus-square-o");
            
            content.show();
            icon.removeClass("fa-plus-square-o")
                .addClass("fa-minus-square-o");   

            var node = this.model.get("tree");
            node = node.first(function (obj) {
                return obj.model.id === nodeId;
            });

            if (!_.isUndefined(node)) {
                node.model.closed = false;
            }
                
        },

        closeContainerForNodeId: function (nodeId) {
            var elem = $('#'+nodeId);
            var content = elem.find(".tree-container-content").first();
            var header = elem.find(".tree-container-header").first();
            var icon = header.find(".fa-minus-square-o");
            
            content.hide();
            icon.removeClass("fa-minus-square-o")
                .addClass("fa-plus-square-o");      

            var node = this.model.get("tree");
            node = node.first(function (obj) {
                return obj.model.id === nodeId;
            });

            if (!_.isUndefined(node)) {
                node.model.closed = true;
            }                
        },

        
        
        openContainer: function (evt) {
            evt.stopPropagation();
            var $el, $content, $header, isClosed, cssclass;
            
            $el = $(evt.target).parents(".tree-container").first();
            $header = $el.find(".tree-container-header").first();
            $content = $el.find(".tree-container-content").first();
            isClosed = $header.find(".fa-plus-square-o").length > 0;

            var that = this;

            if (isClosed) {
                // Check if we must close other nodes before opening this one
                var path = $el.attr("data-path");
                var pathElements = path.split(',');
                $('#nav-tree').find(".fa-minus-square-o").each(function( index ) {
                    var elem = $(this).parent().parent().parent();
                    
                    var id = elem.attr('id');
                    if ( jQuery.inArray( id, pathElements) < 0 ) {
                        that.saveCloseNode(id);
                        that.closeContainerForNodeId(id);
                    }
                });                
            }
            
            this._openContainerAux($el, $content, isClosed);
            if (isClosed) {
                // Open node
                this.saveOpenNode($el.attr("id"));
                this.openContainerForNodeId($el.attr("id"));
            } else {
                // Close node
                this.saveCloseNode($el.attr("id"));
                this.closeContainerForNodeId($el.attr("id"));
            }

        },

        _deleteOU: function () {
            var model = new App.OU.Models.OUModel({ id: this });
            model.fetch({ success: function() {
                model.destroy({
                    success: function () {
                        App.instances.tree.reloadTree();
                    }
               });
            }});
        },

        _pasteOU: function (evt) {
            var modelCut = App.instances.cut,
                modelParent = new App.OU.Models.OUModel({ id: this });

            modelParent.fetch({success: function () {
                //Cant move nodes between domains
                if (modelCut.getDomainId() !== modelParent.getDomainId()) {
                    App.showAlert(
                        "error",
                        gettext("Nodes can not be moved between domains.")
                    );
                    return;
                }
                modelCut.set("path", modelParent.get("path") + "," + modelParent.get("id"));

                modelCut.saveWithToken().done(
                    function () {
                        $("#" + modelCut.get("id")).remove();
                        App.instances.tree.updateNodeById(modelParent.get("id"));
                        App.instances.tree.reloadTree();
                    }
                );
                App.instances.staging.toMove.push([modelCut.get("id"), modelParent.get("id")]);
                App.instances.cut = undefined;
                App.instances.tree.trigger("change");
            }});
        },

        showContainerMenu: function (evt) {
            evt.stopPropagation();
            var $el = $(evt.target),
                ouId = $el.parents(".tree-container").first().attr("id"),
                $html = $(this.renderer._templates.extraOpts({ ouId: ouId })),
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
                    message: gettext("Deleting an OU is a permanent action. " +
                                     "It will also delete all its children.")
                });
            });

            if (App.instances.cut === undefined) {
                $html.find("a.text-warning").parent("li").remove();
            }
            
            var node = App.instances.tree.findNodeById(ouId),
                path = node.path || node.get("path");          
            
            if ($("#tree-container").hasClass('admin') == false && (path === 'root' || path.split(',').length === 2)) {
                $html.find("a.text-danger").parent("li").remove();
            }
            
            $html.find("a.text-warning").click(function (evt) {
                evt.preventDefault();
                _.bind(that._pasteOU, ouId)();
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

            if ( !this.isNodeOpen(id) ) {
                // Clear the saved state and recalculate the state for current selected node
                this.clearSavedState();
                this.calculateStateForNode(id);
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
        },
        
        /**
         * Adds a node to the list of open nodes.
         * @node_id Node ID to add to the list.
         */
        saveOpenNode: function(node_id) {
            if (this.isNodeOpen(node_id)) {
                // Already opened
                return;
            }
            
            var openNodes = {};
            if(jQuery.type(Cookies.get('main_tree_opened_nodes')) != "undefined") {
                openNodes = JSON.parse(Cookies.get('main_tree_opened_nodes'));
            }
            if (jQuery.type(openNodes[username]) == "undefined") {
                openNodes[username] = []
            }
            
            openNodes[username].push(node_id); 
            Cookies.set('main_tree_opened_nodes',  JSON.stringify(openNodes));
            
        },
        
        /**
         * Removes a node to the list of open nodes.
         * @node_id Node ID to remove from the list.
         */
        saveCloseNode: function(node_id) {
            var openNodes = {};
            if(jQuery.type(Cookies.get('main_tree_opened_nodes')) != "undefined") {
                openNodes = JSON.parse(Cookies.get('main_tree_opened_nodes'));
            }
            if (jQuery.type(openNodes[username]) == "undefined") {
                openNodes[username] = []
            }
            
            if (openNodes[username].indexOf(node_id) < 0) {
                return;
            }
            
            openNodes[username].splice(openNodes[username].indexOf(node_id), 1);
            Cookies.set('main_tree_opened_nodes',  JSON.stringify(openNodes));
        },
        
        /**
         * Checks if a node is in the list of open nodes.
         * @node_id Node ID to check.
         * @returns true if the node is in the list.
         */
        isNodeOpen: function(node_id) {
            var openNodes = {};
            if(jQuery.type(Cookies.get('main_tree_opened_nodes')) != "undefined") {
                openNodes = JSON.parse(Cookies.get('main_tree_opened_nodes'));
            }            
            if (jQuery.type(openNodes[username]) == "undefined") {
                openNodes[username] = []
            }
            
            return (openNodes[username].indexOf(node_id) >= 0);
        },
        
        /**
         * Saves the curren page for a Node in the browser cookies.
         * @node_id Node ID.
         * @page Page number.
         */
        setCurrentPageforNode: function(node_id, page) {
            var nodePage = {};
            if(jQuery.type(Cookies.get('main_tree_node_pages')) != "undefined") {
                nodePage = JSON.parse(Cookies.get('main_tree_node_pages'));
            }
            if (jQuery.type(nodePage[username]) == "undefined") {
                nodePage[username] = {}
            }
            
            nodePage[username][node_id] = page; 
            Cookies.set('main_tree_node_pages',  JSON.stringify(nodePage));
            
        },
        
       
        /**
         * Get the current page of a Node from browser cookies.
         * @node_id Node ID.
         */
        getCurrentPageforNode: function(node_id) {
            var nodePage = {};
            if(jQuery.type(Cookies.get('main_tree_node_pages')) != "undefined") {
                nodePage = JSON.parse(Cookies.get('main_tree_node_pages'));
            }            
            if (jQuery.type(nodePage[username]) == "undefined") {
                nodePage[username] = {}
            }
            
            return nodePage[username][node_id];
        },
        
        /**
         * Clears the state saved in cookies.
         */
        clearSavedState: function() {
            Cookies.remove('main_tree_node_pages');
            Cookies.remove('main_tree_opened_nodes');
        },
        
        /**
         * Calculates the saved state for a selected node.
         * @node_id Node ID.
         */
        calculateStateForNode: function(node_id) {
            var nodePage = {};
            if(jQuery.type(Cookies.get('main_tree_node_pages')) != "undefined") {
                nodePage = JSON.parse(Cookies.get('main_tree_node_pages'));
            }            
            if (jQuery.type(nodePage[username]) == "undefined") {
                nodePage[username] = {}
            }
            
            var openNodes = {};
            if(jQuery.type(Cookies.get('main_tree_opened_nodes')) != "undefined") {
                openNodes = JSON.parse(Cookies.get('main_tree_opened_nodes'));
            }            
            if (jQuery.type(openNodes[username]) == "undefined") {
                openNodes[username] = []
            }
            
            var root = this.$el.find(".tree-container").first();
            if (jQuery.type(root) == "undefined" || root.attr('data-path') != "root") {
                // No root element!
                //console.log("No root element!");
                return;
            }
            
            var rootId = root.attr('id');
            
            // Calculate open nodes
            var item = this.$el.find('#' + node_id);
            if (item.length <= 0) {
                // Element not found
                //console.log("Element not found!");
                return;
            }
            
            if (!item.hasClass("tree-container")) {
                // Find the container that contains the item
                item = item.parents(".tree-container").first()
            }
            
            
            // The container ID if it's open
            var isOpen = (item.find(".tree-container-header").first().find(".fa-minus-square-o").length > 0);
            if (isOpen) {
                this.saveOpenNode(node_id);
            }

            // Add the container path
            var path = item.attr('data-path');
            var parts = path.split(',');
            for (var i = 0; i < parts.length; i++) {
                var ou = parts[i];
                if (ou != "root") {
                    this.saveOpenNode(ou);
                }
            }
            
            // Calculate root node page
            var node = this.model.get("tree").first(function (obj) {
                return obj.model.id === rootId;
            });

            var page = 1;
            if (node.model.status === "paginated") {
                page = node.model.paginatedChildren.currentPage;   
            }                
            //console.log('Current page is: '+page);
            
            this.setCurrentPageforNode(rootId, page);
            
        },        
        
        
        
    });
});
