/*jslint browser: true, nomen: true */
/*global $, App, TreeModel */

/*
* Fuel UX Tree
* https://github.com/ExactTarget/fuelux
*
* Copyright (c) 2012 ExactTarget
* Copyright (c) 2013 Junta de Andalucia
* Licensed under the MIT license.
*/

App.module("Tree", function (Tree, App, Backbone, Marionette, $, _) {
    "use strict";

    // TREE CONSTRUCTOR AND PROTOTYPE

    var TreePlugin = function (element, options) {
        this.$element.on('click', '.tree-item', $.proxy(function (ev) { this.selectItem(ev.currentTarget); }, this));
    };

    TreePlugin.prototype = {
        constructor: TreePlugin,

        selectItem: function (el) {
            var $el = $(el);
            var $all = this.$element.find('.tree-selected');
            var data = [];

            if (this.options.multiSelect) {
                $.each($all, function(index, value) {
                    var $val = $(value);
                    if ($val[0] !== $el[0]) {
                        data.push($(value).data());
                    }
                });
            } else if ($all[0] !== $el[0]) {
                $all.removeClass('tree-selected')
                    .find('span').removeClass('fa-check').addClass('fa-user');
                data.push($el.data());
            }

            var eventType = 'selected';
            if ($el.hasClass('tree-selected')) {
                eventType = 'unselected';
                $el.removeClass('tree-selected');
                $el.find('span').removeClass('fa-check').addClass('fa-user');
            } else {
                $el.addClass('tree-selected');
                $el.find('span').removeClass('fa-user').addClass('fa-check');
                if (this.options.multiSelect) {
                    data.push($el.data());
                }
            }

            if (data.length) {
                this.$element.trigger('selected', {info: data});
            }

            // Return new list of selected items, the item
            // clicked, and the type of event:
            $el.trigger('updated', {
                info: data,
                item: $el,
                eventType: eventType
            });
        },

        selectedItems: function () {
            var $sel = this.$element.find('.tree-selected');
            var data = [];

            $.each($sel, function (index, value) {
                data.push($(value).data());
            });
            return data;
        },

        // collapses open folders
        collapse: function () {
            var cacheItems = this.options.cacheItems;

            // find open folders
            this.$element.find('.fa-folder-open').each(function () {
                // update icon class
                var $this = $(this)
                    .removeClass('fa-folder fa-folder-open')
                    .addClass('fa-folder');

                // "close" or empty folder contents
                var $parent = $this.parent().parent();
                var $folder = $parent.children('.tree-folder-content');

                $folder.hide();
                if (!cacheItems) {
                    $folder.empty();
                }
            });
        }
    };


    // TREE PLUGIN DEFINITION

    $.fn.tree = function (option, value) {
        var methodReturn;

        var $set = this.each(function () {
            var $this = $(this);
            var data = $this.data('tree');
            var options = typeof option === 'object' && option;

            if (!data) { $this.data('tree', (data = new TreePlugin(this, options))); }
            if (typeof option === 'string') { methodReturn = data[option](value); }
        });

        return (methodReturn === undefined) ? $set : methodReturn;
    };

    $.fn.tree.defaults = {
        multiSelect: false,
        loadingHTML: '<div>Loading...</div>',
        cacheItems: true
    };

    $.fn.tree.Constructor = TreePlugin;

    App.addInitializer(function (options) {
        App.root = new Tree.Models.TreeData();
        $.ajax("/api/nodes/?maxdepth=10", {
            success: function (response) {
                App.root.parseTree(response);
            }
        });
        var treeView = new Tree.Views.NavigationTree({ model: App.root });
        App.tree.show(treeView);
        App.root.on("change", function () {
            App.tree.show(treeView);
        });
    });
});

App.module("Tree.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.TreeData = Backbone.Model.extend({
        parser: new TreeModel(),

        defaults: {
            tree: null
        },

        parseTree: function (data) {
            var preprocessed = {
                id: "root",
                children: []
            };
            _.each(data, function (node) {
                var newnode = _.clone(node),
                    path = node.path.split(','),
                    aux;

                newnode.id = newnode._id;
                delete newnode._id;

                aux = preprocessed.children;
                _.each(path, function (step) {
                    if (step === "root") { return; }
                    var obj = _.find(aux, function (child) {
                        return child.id === step;
                    });
                    if (!obj) {
                        // This path step is not present, lets create the
                        // container
                        obj = {
                            id: step,
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

            this.set("tree", this.parser.parse(preprocessed));
        },

        toJSON: function () {
            var tree = this.get("tree");
            if (tree) {
                return _.clone(tree.model.children[0]);
            }
            return {};
        }
    });
});

App.module("Tree.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    var treeContainerPre =
            '<div class="tree-folder" style="display: block;" id="<%= id %>">\n' +
            '    <div class="tree-folder-header">\n' +
            '        <span class="fa fa-plus-square-o"></span> ' +
            '        <span class="fa fa-group"></span>\n' +
            '        <div class="tree-folder-name"><%= name %></div>\n' +
            '    </div>\n' +
            '    <div class="tree-folder-content">\n',
        treeContainerPost =
            '    </div>\n' +
            '    <div class="tree-loader" style="display: none;">\n' +
            '        <div class="static-loader">Loading...</div>\n' +
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
                html = "<p><span class='fa fa-spinner fa-spin'></span> Loading...</p>";
            }
            this.$el.html(html);
            return this;
        },

        recursiveRender: function (node) {
            var that = this,
                json = _.pick(node, "name", "type", "id"),
                html;

            if (json.type === "ou") {
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

        selectContainer: function (evt) {
            var $el = $(evt.target).parents(".tree-folder").first(),
                $treeFolderContent = $el.find('.tree-folder-content').first(),
                classToTarget,
                classToAdd;

            if ($el.find('.tree-folder-header').first().find('.fa-plus-square-o').length > 0) {
                classToTarget = '.fa-plus-square-o';
                classToAdd = 'fa-minus-square-o';
                $treeFolderContent.hide();
            } else {
                classToTarget = '.fa-minus-square-o';
                classToAdd = 'fa-plus-square-o';
                $treeFolderContent.show();
            }

            $el.find(classToTarget).first()
                .removeClass('fa-plus-square-o fa-minus-square-o')
                .addClass(classToAdd);
        },

        selectItem: function (evt) {
            var $el = $(evt.target).parents(".tree-item").first(),
                id = $el.attr("id"),
                item;

            item = this.model.get("tree").first(function (node) {
                return node.model.id === id;
            });

            if (item && item.model.type === "user") {
                window.location = "/users/";
            }
        }
    });
});
