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

    var HomeView, Router;

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

    Router = Backbone.Marionette.AppRouter.extend({
        appRoutes: {
            "": "loadHome",
            "byid/:id": "loadById",
            "newroot": "newRoot",
            "ou/:containerid/new": "newItemDashboard",
            "ou/:containerid/user": "newUser",
            "ou/:containerid/user/:userid": "loadUser",
            "ou/:containerid/ou": "newOU",
            "ou/:containerid/ou/:ouid": "loadOU",
            "ou/:containerid/group": "newGroup",
            "ou/:containerid/group/:groupid": "loadGroup",
            "ou/:containerid/computer": "newComputer",
            "ou/:containerid/computer/:computerid": "loadComputer",
            "ou/:containerid/storage": "newStorage",
            "ou/:containerid/storage/:storageid": "loadStorage"
        },

        controller: {
            loadHome: function () {
                var view = new HomeView();
                App.alerts.close();
                App.instances.breadcrumb.setSteps([]);
                App.tree.$el
                    .find(".tree-selected")
                    .removeClass("tree-selected");
                App.main.show(view);
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

            _newItemHelper: function (Model, View, containerid) {
                var model = new Model(),
                    view = new View({ model: model }),
                    parent,
                    path;

                // Render the loader indicator
                App.main.show(App.instances.loaderView);
                if (!(App.instances.tree.has("tree"))) {
                    App.instances.router.navigate("", { trigger: true });
                    return;
                }
                parent = App.instances.tree.get("tree").first(function (n) {
                    return n.model.id === containerid;
                });
                path = parent.model.path + ',' + parent.model.id;
                model.set("path", path);

                App.main.show(view);
            },

            newUser: function (containerid) {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/user",
                    text: gettext("User")
                }]);
                this._newItemHelper(
                    App.User.Models.UserModel,
                    App.User.Views.UserForm,
                    containerid
                );
            },

            newOU: function (containerid) {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([{
                    url: "ou/",
                    text: gettext("Organisational Unit")
                }]);
                this._newItemHelper(
                    App.OU.Models.OUModel,
                    App.OU.Views.OUForm,
                    containerid
                );
            },

            newGroup: function (containerid) {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/group",
                    text: gettext("Group")
                }]);
                this._newItemHelper(
                    App.Group.Models.GroupModel,
                    App.Group.Views.GroupForm,
                    containerid
                );
            },

            newComputer: function (containerid) {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/computer",
                    text: gettext("Computer")
                }]);
                this._newItemHelper(
                    App.Computer.Models.ComputerModel,
                    App.Computer.Views.ComputerForm,
                    containerid
                );
            },

            newStorage: function (containerid) {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/storage",
                    text: gettext("Remote storage")
                }]);
                this._newItemHelper(
                    App.Storage.Models.StorageModel,
                    App.Storage.Views.StorageForm,
                    containerid
                );
            },

            _loadItemHelper: function (Model, View, id) {
                var model, view, skipFetch;

                model = App.instances.cache.get(id);
                if (_.isUndefined(model)) {
                    model = new Model({ id: id });
                    App.instances.cache.set(id, model);
                } else {
                    skipFetch = true;
                }
                view = new View({ model: model });

                // Render the loader indicator
                App.main.show(App.instances.loaderView);
                model
                    .off("change")
                    .on("change", function () {
                        App.main.show(view);
                    });

                if (skipFetch) {
                    model.trigger("change");
                    App.tree.currentView.editLeafById(id);
                } else {
                    model.fetch().done(function () {
                        // Item loaded, now we need to update the tree
                        var node = App.instances.tree.get("tree").first(function (n) {
                                return n.model.id === id;
                            }),
                            promise = $.Deferred();

                        if (node && node.model.loaded) {
                            promise.resolve();
                        } else {
                            promise = App.instances.tree.loadFromNode(
                                model.get("path"),
                                model.get("id"),
                                true
                            );
                        }
                        promise.done(function () {
                            App.tree.currentView.editLeafById(id);
                        });
                    });
                }
            },

            loadUser: function (containerid, userid) {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/user/" + userid,
                    text: gettext("User")
                }]);
                this._loadItemHelper(
                    App.User.Models.UserModel,
                    App.User.Views.UserForm,
                    userid
                );
            },

            loadOU: function (containerid, ouid) {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/ou" + ouid,
                    text: gettext("Organisational Unit")
                }]);
                this._loadItemHelper(
                    App.OU.Models.OUModel,
                    App.OU.Views.OUForm,
                    ouid
                );
            },

            loadGroup: function (containerid, groupid) {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/group/" + groupid,
                    text: gettext("Group")
                }]);
                this._loadItemHelper(
                    App.Group.Models.GroupModel,
                    App.Group.Views.GroupForm,
                    groupid
                );
            },

            loadComputer: function (containerid, computerid) {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/computer/" + computerid,
                    text: gettext("Computer")
                }]);
                this._loadItemHelper(
                    App.Computer.Models.ComputerModel,
                    App.Computer.Views.ComputerForm,
                    computerid
                );
            },

            loadStorage: function (containerid, storageid) {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/storage/" + storageid,
                    text: gettext("Remote storage")
                }]);
                this._loadItemHelper(
                    App.Storage.Models.StorageModel,
                    App.Storage.Views.StorageForm,
                    storageid
                );
            }
        }
    });

    App.instances.router = new Router();

    App.on('initialize:after', function () {
        var path = window.location.hash.substring(1);

        if (Backbone.history) {
            Backbone.history.start();
        }

        App.instances.router.navigate(path, { trigger: true });
    });
}(Backbone, jQuery, _, gettext));
