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

(function (Backbone, $, _, gettext, MessageManager) {
    "use strict";

    var HomeView, NewElementView, LoaderView, Router, JobsView;

    App = new Backbone.Marionette.Application();

    // To store references to root instances
    App.instances = {};

    App.addRegions({
        // sidebar
        tree: "#ex-tree",
        events: "#events-container",
        // main area
        breadcrumb: "#breadcrumb",
        alerts: "#alerts-area",
        main: "#viewport-main"
    });

    JobsView = Backbone.Marionette.ItemView.extend({
        template: "#jobs-template",
        id: 'events',
        className: 'panel panel-default bootstrap-admin-no-table-panel',
        events: {
            "click #maximize": "maximize",
            "click #minimize": "minimize",
            "click button.refresh": "refresh",
            "click ul.pagination a": "goToPage"
        },

        refresh: function () {
            App.instances.job_collection.fetch();
        },
        maximize: function (evt) {
            var events = this.$el;
            evt.preventDefault();
            events.find("#maximize").addClass("hide");
            events.find("#minimize").removeClass("hide");
            $(document.body).append(events);
            events.find(".short").addClass("hide");
            events.find(".long").removeClass("hide");
            events.addClass("maximize");
        },
        minimize: function(evt) {
            var events = this.$el;
            evt.preventDefault();
            events.find("#maximize").removeClass("hide");
            events.find("#minimize").addClass("hide");
            $("#sidebar").append(events);
            events.find(".short").removeClass("hide");
            events.find(".long").addClass("hide");
            events.removeClass("maximize");
        },
        serializeData: function(){
            var paginator = [],
                inRange = this.collection.pagesInRange,
                pages = inRange * 2 + 1,
                current = this.collection.currentPage,
                total = this.collection.totalPages,
                i = 0,
                page;

            for (i; i < pages; i += 1) {
                page = current - inRange + i;
                if (page > 0 && page <= total) {
                    paginator.push([page, page === current]);
                }
            }
            return {
                "iconClasses": App.Tree.Views.iconClasses,
                "items": this.collection.toJSON(),
                "totalPages": this.collection.totalPages,
                "prev": current !== 1,
                "next": current !== total,
                "pages": paginator,
                "showPaginator": paginator.length > 0
            }
        },
        goToPage: function (evt) {
            evt.preventDefault();
            var $el = $(evt.target),
                that = this,
                page;

            if ($el.parent().is(".disabled")) { return; }
            if ($el.is(".previous")) {
                page = this.collection.currentPage - 1;
            } else if ($el.is(".next")) {
                page = this.collection.currentPage + 1;
            } else {
                page = parseInt($el.text(), 10);
            }
            this.collection.goTo(page, {
                success: function () {
                    that.render();
                }
            });
        },
        initialize: function(options) {
            this.collection.on('sync', function() {
             this.render();
            }, this);
        }
    });

    HomeView = Backbone.Marionette.ItemView.extend({
        template: "#home-template",

        initialize: function(options) {
            this.collection.on('sync', function() {
             this.render();
            }, this);
        },
        serializeData: function(){
            return {
                "success": this.collection.where({status: 'finished'}).length,
                "error": this.collection.where({status: 'errors'}).length,
                "processing": this.collection.where({status: 'processing'}).length,
                "total": this.collection.length
            }
        },
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
            "ou/:containerid/:type/:itemid": "loadItem",
            "ou/:containerid/:type/:itemid/policy": "newPolicy",
            "ou/:containerid/:type/:itemid/policy/:policyid": "loadPolicy",
            "search/:keyword": "search"
        },

        controller: {
            loadHome: function () {
                App.alerts.close();
                App.instances.breadcrumb.setSteps([]);
                App.tree.$el
                    .find(".tree-selected")
                    .removeClass("tree-selected");
                if (_.isUndefined(App.instances.job_collection)) {
                    App.instances.job_collection = new App.Job.Models.JobCollection();
                    App.instances.job_collection.fetch();
                }
                App.main.show(new HomeView({collection: App.instances.job_collection}));
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
                storage: gettext("Remote Storage"),
                repository: gettext("Software Repository")
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
                    storage: [App.Storage.Models.StorageModel, App.Storage.Views.StorageForm],
                    repository: [App.Repository.Models.RepositoryModel, App.Repository.Views.RepositoryForm]
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
                model
                    .off("policiesloaded")
                    .once("policiesloaded", function () {
                        if (_.has(view, "policiesList")) {
                            view.policiesList.render();
                        }
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

            newPolicy: function (containerid, type, itemid) {
                var resource = App.instances.cache.get(itemid),
                    url = "ou" + containerid + '/' + type + '/' + itemid,
                    view;

                if (_.isUndefined(resource)) {
                    App.showAlert(
                        "error",
                        gettext("Policies can't be directly accessed."),
                        gettext("You need to load the node that has the policy assigned first. Try again now.")
                    );
                    App.instances.router.navigate(url, { trigger: true });
                    return;
                }

                App.instances.breadcrumb.addStep(url + '/policy/',
                                                 gettext('Add policy'));
                App.main.show(App.instances.loaderView);

                view = new App.Policies.Views.AllPoliciesWidget({
                    resource: resource
                });
                App.main.show(view);
            },

            loadPolicy: function (containerid, type, itemid, policyid) {
                var resource = App.instances.cache.get(itemid),
                    policy = App.instances.cache.get(policyid),
                    promise = $.Deferred(),
                    url = "ou" + containerid + '/' + type + '/' + itemid;

                if (_.isUndefined(resource)) {
                    App.showAlert(
                        "error",
                        gettext("Policies can't be directly accessed."),
                        gettext("You need to load the node that has the policy assigned first. Try again now.")
                    );
                    App.instances.router.navigate(url, { trigger: true });
                    return;
                }

                App.instances.breadcrumb.addStep(url + '/policy/' + policyid,
                                                 gettext('Policy'));
                App.main.show(App.instances.loaderView);

                if (_.isUndefined(policy) || policy.get('is_emitter_policy')) {
                    policy = new App.Policies.Models.PolicyModel({ id: policyid, ou_id: containerid, item_id: itemid });
                    promise = policy.fetch();
                    App.instances.cache.set(policyid, policy);
                } else {
                    promise.resolve();
                }

                promise.done(function () {
                    var view = new App.Policies.Views.PolicyGenericForm({
                        model: policy,
                        resource: resource
                    });
                    App.main.show(view);
                });
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
        if (_.isUndefined(App.instances.job_collection)) {
            App.instances.job_collection = new App.Job.Models.JobCollection();
            App.instances.job_collection.fetch();
        }
        App.events.show(new JobsView({collection: App.instances.job_collection}));
    });

    App.instances.message_manager = MessageManager();
    App.instances.message_manager.bind('change', function(obj) {
        App.instances.cache.drop(obj._id);
        App.trigger('action_change', obj);
    });
    App.instances.message_manager.bind('delete', function(obj) {
        App.instances.cache.drop(obj._id);
        App.trigger('action_delete', obj);
    });
    App.instances.message_manager.bind('jobs', function(obj) {
        App.instances.job_collection.fetch();
    });
}(Backbone, jQuery, _, gettext, MessageManager));
