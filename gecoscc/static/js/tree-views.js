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
            var $search = $("#tree-search");

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
                    var keyword = $search.val().trim();
                    //empty search reload tree
                    if (!keyword) {
                        App.instances.tree.loadFromPath("root");
                    } else {
                        App.instances.router.navigate("search/" + keyword,
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
            var that, $el, prev, node, page, searchId, id;

            that = this;
            $el = $(evt.target);
            if (!$el.is(".tree-pagination")) {
                $el = $el.parents(".tree-pagination").first();
            }
            prev = $el.data("pagination") === "up";
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
                $content.html(this.renderer._loader());
                this.model.loadFromPath(path + ',' + id);
            }
        },

        openContainer: function (evt) {
            evt.stopPropagation();
            var $el, $content, $header, $icon, opened, cssclass;

            $el = $(evt.target).parents(".tree-container").first();
            $content = $el.find(".tree-container-content").first();
            $header = $el.find(".tree-container-header").first();
            opened = $header.find(".fa-plus-square-o").length > 0;

            this._openContainerAux($el, $content, opened);
            if (opened) {
                $icon = $header.find(".fa-plus-square-o");
                $content.show();
                cssclass = "fa-minus-square-o";
            } else {
                $icon = $header.find(".fa-minus-square-o");
                $content.hide();
                cssclass = "fa-plus-square-o";
            }

            $icon
                .removeClass("fa-plus-square-o fa-minus-square-o")
                .addClass(cssclass);
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
