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
        this.$element = $(element);
        this.options = $.extend({}, $.fn.tree.defaults, options);

        this.$element.on('click', '.tree-item', $.proxy(function (ev) { this.selectItem(ev.currentTarget); }, this));
        this.$element.on('click', '.tree-folder-header', $.proxy(function (ev) { this.selectFolder(ev.currentTarget); }, this));

        this.render();
    };

    TreePlugin.prototype = {
        constructor: TreePlugin,

        render: function () {
            this.populate(this.$element);
        },

        populate: function ($el) {
            var self = this;
            var $parent = $el.parent();
            var loader = $parent.find('.tree-loader:eq(0)');

            loader.show();
            this.options.dataSource.data($el.data(), function (items) {
                loader.hide();

                $.each(items.data, function (index, value) {
                    var $entity;

                    if (value.type === "folder") {
                        $entity = self.$element.find('.tree-folder:eq(0)').clone().show();
                        $entity.find('.tree-folder-name').html(value.name);
                        $entity.find('.tree-loader').html(self.options.loadingHTML);
                        $entity.find('.tree-folder-header').data(value);
                    } else if (value.type === "item") {
                        $entity = self.$element.find('.tree-item:eq(0)').clone().show();
                        $entity.find('.tree-item-name').html(value.name);
                        $entity.data(value);
                    }

                    // Decorate $entity with data making the element
                    // easily accessable with libraries like jQuery.
                    //
                    // Values are contained within the object returned
                    // for folders and items as dataAttributes:
                    //
                    // {
                    //     name: "An Item",
                    //     type: 'item',
                    //     dataAttributes = {
                    //         'classes': 'required-item red-text',
                    //         'data-parent': parentId,
                    //         'guid': guid
                    //     }
                    // };

                    var dataAttributes = value.dataAttributes || [];
                    $.each(dataAttributes, function(key, value) {
                        switch (key) {
                        case 'class':
                        case 'classes':
                        case 'className':
                            $entity.addClass(value);
                            break;

                        // id, style, data-*
                        default:
                            $entity.attr(key, value);
                            break;
                        }
                    });

                    if ($el.hasClass('tree-folder-header')) {
                        $parent.find('.tree-folder-content:eq(0)').append($entity);
                    } else {
                        $el.append($entity);
                    }
                });

                // return newly populated folder
                self.$element.trigger('loaded', $parent);
            });
        },

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

        selectFolder: function (el) {
            var $el = $(el);
            var $parent = $el.parent();
            var $treeFolderContent = $parent.find('.tree-folder-content');
            var $treeFolderContentFirstChild = $treeFolderContent.eq(0);

            var eventType, classToTarget, classToAdd;
            if ($el.find('.fa-folder').length) {
                eventType = 'opened';
                classToTarget = '.fa-folder';
                classToAdd = 'fa-folder-open';

                $treeFolderContentFirstChild.show();
                if (!$treeFolderContent.children().length) {
                    this.populate($el);
                }
            } else {
                eventType = 'closed';
                classToTarget = '.fa-folder-open';
                classToAdd = 'fa-folder';

                $treeFolderContentFirstChild.hide();
                if (!this.options.cacheItems) {
                    $treeFolderContentFirstChild.empty();
                }
            }

            $parent.find(classToTarget).eq(0)
                .removeClass('fa-folder fa-folder-open')
                .addClass(classToAdd);

            this.$element.trigger(eventType, $el.data());
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
        $.ajax("/api/nodes/?maxdepth=4", {
            success: function (response) {
                App.root.parseTree(response);
            }
        });
        var treeView = new Tree.Views.NavigationTree({ model: App.root });
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
            '<div class="tree-folder" style="display: block;">\n' +
            '    <div class="tree-folder-header">\n' +
            '        <span class="fa fa-folder"></span>\n' +
            '        <div class="tree-folder-name"><%= name %></div>\n' +
            '    </div>\n' +
            '    <div class="tree-folder-content">\n',
        treeContainerPost =
            '    </div>\n' +
            '    <div class="tree-loader" style="display: none;">\n' +
            '        <div class="static-loader">Loading...</div>\n' +
            '    </div>\n' +
            '</div>';


    Views.NavigationTree = Marionette.ItemView.extend({
        templates: {
            cpre: _.template(treeContainerPre),
            cpost: _.template(treeContainerPost)
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
                json = _.pick(node, "name", "type"),
                html;

            html = this.templates.cpre(json);
            _.each(node.children, function (child) {
                html += that.recursiveRender(child);
            });
            html += this.templates.cpost(json);

            return html;
        }
    });
});
