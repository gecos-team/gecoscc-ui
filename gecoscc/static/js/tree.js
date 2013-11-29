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

    App.addInitializer(function (options) {
        App.root = new Tree.Models.TreeData(); // TODO
        $.ajax("/api/nodes/?maxdepth=1", {
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
                newnode.loaded = true;

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
                            type: "ou",
                            name: "unknown",
                            loaded: false,
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
            '        <span class="fa fa-<%= controlIcon %>-square-o"></span> ' +
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
                json.controlIcon = "plus";
                if (node.loaded && node.children.length > 0) {
                    json.controlIcon = "minus";
                }
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

            if ($el.find('.tree-folder-header').first().find('.fa-minus-square-o').length > 0) {
                classToTarget = '.fa-minus-square-o';
                classToAdd = 'fa-plus-square-o';
                $treeFolderContent.hide();
            } else {
                classToTarget = '.fa-plus-square-o';
                classToAdd = 'fa-minus-square-o';
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
