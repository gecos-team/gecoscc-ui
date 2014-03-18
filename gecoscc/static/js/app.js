/*jslint browser: true, vars: false, nomen: true */
/*global App: true, Backbone, jQuery, _, gettext */

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

// This file creates the global App variable, it should be loaded as soon as
// possible
var App;

(function (Backbone, $, _, gettext) {
    "use strict";

    var HomeView, NewElementView, LoaderView, Router;

    App = new Backbone.Marionette.Application();

    // To store references to root instances
    App.instances = {};

    App.addRegions({
        // sidebar
        tree: "#ex-tree",
        events: "#events",
        // main area
        breadcrumb: "#breadcrumb",
        alerts: "#alerts-area",
        main: "#viewport-main"
    });

    HomeView = Backbone.Marionette.ItemView.extend({
        template: "#home-template",

        onRender: function () {
            this.$el.find('.easyPieChart').easyPieChart({
                animate: 1000
            });
        }
    });

    NewElementView = Backbone.Marionette.ItemView.extend({
        template: "#new-element-template",

        serializeData: function () {
            // This view needs no model
            return {
                ouID: this.containerId
            };
        }
    });

    App.instances.newElementView = new NewElementView();

    LoaderView = Backbone.Marionette.ItemView.extend({
        template: "#loader-template",

        serializeData: function () {
            return {}; // This view needs no model
        }
    });

    App.instances.loaderView = new LoaderView();

    Router = Backbone.Marionette.AppRouter.extend({
        appRoutes: {
            "": "loadHome",
            "byid/:id": "loadById",
            "newroot": "newRoot",
            "ou/:containerid/new": "newItemDashboard",
            "ou/:containerid/:type": "newItem",
            "ou/:containerid/:type/:userid": "loadItem",
            "search/:keyword": "search"
        },

        controller: {
            loadHome: function () {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([]);
                App.tree.$el
                    .find(".tree-selected")
                    .removeClass("tree-selected");
                App.main.show(new HomeView());
            },

            newRoot: function () {
                var model = new App.OU.Models.OUModel({ path: "root" }),
                    view = new App.OU.Views.OUForm({ model: model });
                App.main.show(view);
            },

            loadById: function (id) {
                var model = App.instances.cache.get(id),
                    parent,
                    url;

                App.main.show(App.instances.loaderView);
                if (_.isUndefined(model)) {
                    $.ajax("/api/nodes/" + id + '/').done(function (response) {
                        parent = _.last(response.path.split(','));
                        url = "ou/" + parent + "/" + response.type + "/" + id;
                        App.instances.router.navigate(url, { trigger: true });
                    });
                } else {
                    parent = _.last(model.get("path").split(','));
                    url = "ou/" + parent + "/" + model.get("type") + "/" + id;
                    App.instances.router.navigate(url, { trigger: true });
                }
            },

            newItemDashboard: function (containerid) {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/new",
                    text: gettext("New element")
                }]);

                App.instances.newElementView.containerId = containerid;
                App.main.show(App.instances.newElementView);
            },

            _supportedTypes: {
                user: gettext("User"),
                ou: gettext("Organisational Unit"),
                group: gettext("Group"),
                computer: gettext("Computer"),
                printer: gettext("Printer"),
                storage: gettext("Remote Storage")
            },

            _typeClasses: function (type) {
                // This is a function so it doesn't try to access to the User,
                // OU, etc modules before they are loaded
                return {
                    user: [App.User.Models.UserModel, App.User.Views.UserForm],
                    ou: [App.OU.Models.OUModel, App.OU.Views.OUForm],
                    group: [App.Group.Models.GroupModel, App.Group.Views.GroupForm],
                    computer: [App.Computer.Models.ComputerModel, App.Computer.Views.ComputerForm],
                    printer: [App.Printer.Models.PrinterModel, App.Printer.Views.PrinterForm],
                    storage: [App.Storage.Models.StorageModel, App.Storage.Views.StorageForm]
                }[type];
            },

            _prepare: function (containerid, type, itemid) {
                var url;

                if (!_.has(this._supportedTypes, type)) {
                    App.instances.router.navigate("", { trigger: true });
                    throw "Unknown resource type: " + type;
                }

                App.alerts.close();

                url = "ou/" + containerid + '/' + type;
                if (itemid) { url += '/' + itemid; }

                App.instances.breadcrumb.setSteps([{
                    url: url,
                    text: this._supportedTypes[type]
                }]);
            },

            newItem: function (containerid, type) {
                var Model, model, View, view, parent, path;

                this._prepare(containerid, type);
                Model = this._typeClasses(type)[0];
                model = new Model();
                View = this._typeClasses(type)[1];
                view = new View({ model: model });

                // Render the loader indicator
                App.main.show(App.instances.loaderView);
                if (!(App.instances.tree.has("tree"))) {
                    App.instances.router.navigate("", { trigger: true });
                    return;
                }
                parent = App.instances.tree.findNodeById(containerid);
                path = parent.path + ',' + parent.id;
                model.set("path", path);

                App.main.show(view);
            },

            _fetchModel: function (model) {
                model.fetch().done(function () {
                    // Item loaded, now we need to update the tree
                    var parentId = _.last(model.get("path").split(',')),
                        parentNode = App.instances.tree.get("tree").first(function (n) {
                            return n.model.id === parentId;
                        }),
                        promises = [$.Deferred()];

                    if (!_.isUndefined(parentNode) && parentNode.model.status === "paginated") {
                        promises[0].resolve();
                    } else {
                        promises = App.instances.tree.loadFromPath(
                            model.get("path"),
                            model.get("id"),
                            true
                        );
                    }

                    $.when.apply($, promises).done(function () {
                        App.instances.tree.openAllContainersFrom(
                            _.last(model.get("path").split(',')),
                            true
                        );
                        App.instances.tree.trigger("change");
                    });
                });
            },

            loadItem: function (containerid, type, itemid) {
                var Model, model, View, view, skipFetch;

                this._prepare(containerid, type, itemid);
                App.tree.currentView.activeNode = itemid;
                model = App.instances.cache.get(itemid);
                if (_.isUndefined(model)) {
                    Model = this._typeClasses(type)[0];
                    model = new Model({ id: itemid });
                    App.instances.cache.set(itemid, model);
                } else {
                    skipFetch = true;
                }
                View = this._typeClasses(type)[1];
                view = new View({ model: model });

                // Render the loader indicator
                App.main.show(App.instances.loaderView);
                model
                    .off("change")
                    .once("change", function () {
                        App.main.show(view);
                    });

                if (skipFetch) {
                    // The object was cached
                    App.instances.tree.openAllContainersFrom(
                        _.last(model.get("path").split(',')),
                        true
                    );
                    App.instances.tree.trigger("change");
                    model.trigger("change");
                } else {
                    this._fetchModel(model);
                }
            },

            search: function (keyword) {
                var data = new App.Tree.Models.Search({ keyword: keyword }),
                    view = new App.Tree.Views.SearchResults({
                        collection: data,
                        treeView: App.tree.currentView
                    });

                data.goTo(1, {
                    success: function () {
                        App.tree.show(view);
                    }
                });
            }
        }
    });

    App.instances.router = new Router();

    App.instances.treePromise = $.Deferred();
    App.instances.treePromise.done(function () {
        if (Backbone.history) {
            Backbone.history.start();
        }
    });
}(Backbone, jQuery, _, gettext));
