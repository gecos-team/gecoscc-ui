/*jslint browser: true, vars: false, nomen: true */
/*global App: true, Backbone, jQuery, _, gettext, MessageManager */

/*
* Copyright 2013, Junta de Andalucia
* http://www.juntadeandalucia.es/
*
* Authors:
*   Alberto Beiztegui <albertobeiz@gmail.com>
*   Alejandro Blanco <alejandro.b.e@gmail.com>
*   Pablo Martin <goinnn@gmail.com>
*   Emilio Sanchez <emilio.sanchez@gmail.com>
*
* All rights reserved - EUPL License V 1.1
* https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
*/

// This file creates the global App variable, it should be loaded as soon as
// possible
var App;


(function (Backbone, $, _, gettext, MessageManager) {
    "use strict";

    var HomeView, NewElementView, LoaderView, Router, JobsView, JobsSummaryView, NotFoundView;

    App = new Backbone.Marionette.Application();

    // To store references to root instances
    App.instances = {};

    App.addRegions({
        // sidebar
        tree: "#ex-tree",
        events: "#events-container",
        eventsSummary: "#events-summary-container",
        // main area
        breadcrumb: "#breadcrumb",
        alerts: "#alerts-area",
        main: "#viewport-main"
    });

    JobsView = Backbone.Marionette.ItemView.extend({
        template: "#jobs-template",
        id: 'events',
        className: 'panel panel-default bootstrap-admin-no-table-panel maximize',
        events: {
            "click #minimize": "minimize",
            "click #tasksChilds": "tasksChilds",
            "click button.refresh": "refresh",
            "click ul.pagination a": "goToPage",
            "click span.filters #tasksAll": "tasksAll",
            "click span.filters #tasksProcessing": "tasksProcessing",
            "click span.filters #tasksFinished": "tasksFinished",
            "click span.filters #tasksErrors": "tasksErrors",
            "click span.filters #tasksWarnings": "tasksWarnings",
            "click span.filters #tasksActives": "tasksActives",
            "click span.filters #tasksArchived": "tasksArchived",
            "click button.archiveTasks": "archiveTasks",
            "click button.backstack": "backstack",
            "click button.tasks-search-btn": "tasksSearch",
            "switchChange.bootstrapSwitch #seeAll": "seeAll",
            "keydown .tasks-search-input":"pressEnter",
        },

        pressEnter: function(evt) {
            var code = evt.keyCode || evt.which;
            if(code == 13) { 
                this.tasksSearch();
            }
        },

        tasksSearch: function() {
            this.collection.userfilter  = this.$el.find('#tasksByUser').val().trim() || undefined;
            this.collection.workstation = this.$el.find('#tasksByWorkstation').val().trim() || undefined;
            this.collection.source      = this.$el.find("#tasksBySource").val().trim() || undefined; 
            this.tasksFilter();
        },
        seeAll: function(evt, data) {
            evt.preventDefault();
            this.collection.seeAll = data;
            this.collection.archived = false;
            this.tasksFilter();
        },
        backstack: function () {                                
            this.collection.status = '';
            this.collection.archived = false;
            this.collection.parentId = '';
            this.tasksFilter();
        },
        refresh: function () {
            App.instances.job_collection.fetch();
            App.instances.job_statistics.fetch();
            App.instances.myjob_statistics.fetch();
        },
        tasksFilter: function () {
            this.collection.currentPage = 1;
            this.refresh();
        },
        tasksAll: function (evt) {
            evt.preventDefault();
            this.collection.status = '';
            this.collection.archived = false;
            this.tasksFilter();
        },
        tasksProcessing: function (evt) {
            evt.preventDefault();
            this.collection.status = 'processing';
            this.collection.archived = false;
            this.tasksFilter();
        },
        tasksFinished: function (evt) {
            evt.preventDefault();
            this.collection.status = 'finished';
            this.collection.archived = false;
            this.tasksFilter();
        },
        tasksErrors: function (evt) {
            evt.preventDefault();
            this.collection.status = 'errors';
            this.collection.archived = false;
            this.tasksFilter();
        },
        tasksWarnings: function (evt) {
            evt.preventDefault();
            this.collection.status = 'warnings';
            this.collection.archived = false;
            this.tasksFilter();
        },
        tasksActives: function (evt) {
            evt.preventDefault();
            this.collection.status = '';
            this.collection.archived = false;
            this.tasksFilter();
        },
        tasksArchived: function (evt) {
            evt.preventDefault();
            this.collection.status = '';
            this.collection.archived = true;
            this.tasksFilter();
        },
        tasksChilds: function (evt) {
            evt.preventDefault();
            this.collection.parentId = evt.currentTarget.innerHTML;
            this.tasksFilter();
        },
        archiveTasks: function (evt) {
            var that = this;
            evt.preventDefault();
            $.ajax({
                url: '/api/archive_jobs/',
                type: 'PUT',
                success: function () {
                    that.tasksFilter();
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

        minimize: function (evt) {
            evt.preventDefault();
            
            // Hide maximized events container
            $('#events-container').hide();            
            
            // Show events summary
            $('#events-summary-container').show();
            
            // Show main area
            $('#main-area').show();
        },
        
        serializeData: function () {
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
                "getIcon": App.Tree.Views.getIcon,
                "items": this.collection.toJSON(),
                "totalPages": total,
                "initial": current > inRange + 1,
                "final": current < total - inRange,
                "prev": current !== 1,
                "next": current !== total,
                "pages": paginator,
                "showPaginator": paginator.length > 1,
                "status": this.collection.status,
                "parentId":this.collection.parentId,
                "archived": this.collection.archived,
                "total": this.collection.total,
                "workstation": this.collection.workstation,
                "userfilter": this.collection.userfilter,
                "source": this.collection.source,
            };
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
            return false;
        },
        initialize: function () {
            this.collection.status = '';
            this.collection.on('sync', function () {
                this.render();
            }, this);
        },
        onRender: function() {
            var $button = this.$el.find('div.seeAll'),
                that = this;
            if ($button.hasClass('admin') == false) {
                $button.addClass('hidden');
            } else {
                $("[name='seeAll']").bootstrapSwitch('state', this.collection.seeAll, true);
            }
            if (this.collection.source || this.collection.userfilter || this.collection.workstation) {
                if (!_.isUndefined(this.collection.source)) {
                    $('#tasksBySource-close-search-btn').removeClass('hidden');
                }

                if (!_.isUndefined(this.collection.userfilter)) {
                    $('#tasksByUser-close-search-btn').removeClass('hidden');
                }

                if (!_.isUndefined(this.collection.workstation)) {
                    $('#tasksByWorkstation-close-search-btn').removeClass('hidden');
                }

                var that = this
                $(".tasks-close-search-btn").each( function() {
                    $(this).click(function (evt) {
                        evt.preventDefault();
                        switch (this.id) {
                            case 'tasksBySource-close-search-btn':
                                that.collection.source = undefined;
                                $(this).addClass('hidden');
                                break;
                            case 'tasksByUser-close-search-btn':
                                that.collection.userfilter = undefined;
                                $(this).addClass('hidden');
                                break;
                            case 'tasksByWorkstation-close-search-btn':
                                that.collection.workstation = undefined;
                                $(this).addClass('hidden');
                                break;
                        }
                        that.tasksFilter();
                     });
                });
            }
        }
    });

    JobsSummaryView = Backbone.Marionette.ItemView.extend({
        template: "#jobs-summary-template",
        id: 'events_summary',
        className: 'panel panel-default bootstrap-admin-no-table-panel',
        events: {
            "click #maximize": "maximize",
            "click button.refresh": "refresh",
            "click button.archiveTasks": "archiveTasks",
        },

        refresh: function () {
            App.instances.job_collection.fetch();
            App.instances.job_statistics.fetch();
            App.instances.myjob_statistics.fetch();
        },
        
        archiveTasks: function (evt) {
            var that = this;
            evt.preventDefault();
            $.ajax({
                url: '/api/archive_jobs/',
                type: 'PUT',
                success: function () {
                    that.tasksFilter();
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
        
        maximize: function (evt) {
            evt.preventDefault();
            
            // Hide events summary
            $('#events-summary-container').hide();
            
            // Hide main area
            $('#main-area').hide();
            
            // Show maximized events container
            $('#events-container').show();
        },        
        
        

        initialize: function () {
            this.model.on('sync', function () {
                this.render();
            }, this);
        },
        serializeData: function () {
            return {
                "finished": this.model.attributes.finished,
                "errors": this.model.attributes.errors,
                "processing": this.model.attributes.processing,
                "total": this.model.attributes.total
            };
        },
        onRender: function () {
            this.$el.find('.easyPieChart').each(function(){
                var pieChart = $(this);
                
                pieChart.easyPieChart({
                    animate: 1000,
                    size: 60,                
                    barColor:  pieChart.attr('bar-color')
                });
                
            });
        }
    });
    
    
    HomeView = Backbone.Marionette.ItemView.extend({
        template: "#home-template",

        initialize: function () {
            this.model.on('sync', function () {
                this.render();
            }, this);
        },
        serializeData: function () {
            return {
                "finished": this.model.attributes.finished,
                "errors": this.model.attributes.errors,
                "processing": this.model.attributes.processing,
                "total": this.model.attributes.total
            };
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
            var model = App.instances.tree.findNodeById(this.containerId),
                isFirstLevel = false;
            if (model && model.path === "root") {
                isFirstLevel = true;
            }
            return {
                ouID: this.containerId,
                isGecosMaster: this.isGecosMaster,
                isFirstLevel: isFirstLevel
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
            "ou/:containerid/:type/:itemid/policy": "newPolicy",
            "ou/:containerid/:type/:itemid(/:tab)": "loadItem",
            "ou/:containerid/:type/:itemid/policy/:policyid": "loadPolicy",
            "search/:keyword": "search",
            "logbook": "logbook"                                
        },

        controller: {
            logbook: function () {
                if (_.isUndefined(App.instances.job_collection)) {
                    App.instances.job_collection = new App.Job.Models.JobCollection();
                    App.instances.job_collection.fetch();
                }
                if (_.isUndefined(App.instances.job_statistics)) {
                    App.instances.job_statistics = new App.Job.Models.JobStatistics();
                    App.instances.job_statistics.fetch();
                }
                if (_.isUndefined(App.instances.myjob_statistics)) {
                    App.instances.myjob_statistics = new App.Job.Models.MyJobStatistics();
                    App.instances.myjob_statistics.fetch();
                }
                
                
                App.events.show(new JobsView({collection: App.instances.job_collection}));
                App.eventsSummary.show(new JobsSummaryView({model: App.instances.myjob_statistics}));                
                
                // Hide events summary
                $('#events-summary-container').hide();
                
                // Hide main area
                $('#main-area').hide();
                
                // Show maximized events container
                $('#events-container').show();
            },
            
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
                if (_.isUndefined(App.instances.job_statistics)) {
                    App.instances.job_statistics = new App.Job.Models.JobStatistics();
                    App.instances.job_statistics.fetch();
                }
                if (_.isUndefined(App.instances.myjob_statistics)) {
                    App.instances.myjob_statistics = new App.Job.Models.MyJobStatistics();
                    App.instances.myjob_statistics.fetch();
                }
                App.main.show(new HomeView({model: App.instances.job_statistics}));
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
                App.alerts.close();
                App.main.show(App.instances.loaderView);
                if (_.isUndefined(model)) {
                    $.ajax({ url:"/api/nodes/" + id + '/', statusCode: {
                        403: function() {
                          forbidden_access();
                        }
					}}).done(function (response) {
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
                var domain = App.getDomainModel(containerid);
                domain.fetch().done(function () {
                    App.instances.newElementView.containerId = containerid;
                    App.instances.newElementView.isGecosMaster = domain.get("master") === "gecos";
                    App.main.show(App.instances.newElementView);
                });
                App.alerts.close();
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/new",
                    text: gettext("New element")
                }]);
            },

            _supportedTypes: {
                user: gettext("User"),
                ou: gettext("Organisational Unit"),
                group: gettext("Group"),
                computer: gettext("Workstation"),
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
                var Model, model, View, view, parent, path, domain,
                    that = this;

                //First Level Ous can create onlly OUs
                model = App.instances.tree.findNodeById(containerid);
                if (model && model.path === "root" && type !== "ou") {
                    App.instances.router.navigate("ou/" + containerid + "/new", { trigger: true });
                    App.showAlert(
                        "error",
                        gettext("First level OUs can only add new OUs.")
                    );
                    return;
                }

                //check if master is gecoss
                domain =  App.getDomainModel(containerid);
                domain.fetch().done(function () {

                    //if not gecos only users can be added
                    if (domain.get("master") !== "gecos" && type !== "user") {
                        App.instances.router.navigate("ou/" + containerid + "/new", { trigger: true });
                        App.showAlert(
                            "error",
                            gettext("Domain is not Gecos."),
                            gettext("Only local users can be added.")
                        );
                        return;
                    }

                    that._prepare(containerid, type);
                    Model = that._typeClasses(type)[0];
                    model = new Model();
                    View = that._typeClasses(type)[1];
                    view = new View({ model: model });

                    // Render the loader indicator
                    App.main.show(App.instances.loaderView);
                    if (!(App.instances.tree.has("tree"))) {
                        App.instances.router.navigate("", { trigger: true });
                        return;
                    }
                    parent = App.instances.tree.findNodeById(containerid);
                    path = (parent.path || parent.get('path')) + ',' + parent.id;
                    model.set("path", path);

                    App.main.show(view);
                });
            },

            _fetchModel: function (model) {
                model.fetch().done(function () {
                    var children = App.instances.tree.get("tree").children,
                        isRoot = _.some(children, function (child) {
                            return child.model.id === model.id;
                        }),
                        isVisible = !_.isUndefined(App.instances.tree.findNodeById(model.id));

                    if (!isRoot && !isVisible) {
                        App.tree.currentView.closeAllExcept(model.get("path"));
                        App.instances.tree.loadFromPath(
                            model.get("path"),
                            model.get("id"),
                            false
                        );
                    } else {
                        App.tree.currentView.closeAllExcept(model.get("path"));
                        App.instances.tree.openPath(
                            model.get("path")
                        );
                    }
                    App.instances.cache.set(model.get('id'), model);

                }).fail( function( jqXHR, textStatus, errorThrown ) {
                  if (jqXHR.status === 403) {
                    forbidden_access();
                  }
                  else {
                    console.log('Error: '+jqXHR.status+' '+jqXHR.statusText+' - '+textStatus+' - '+errorThrown);
                    App.main.close(App.instances.loaderView);
                    App.showAlert(
                            "error",
                            gettext("¡¡ OOOOOPSSS !! The url points to a non-existent object."),
                            "<br/> - " + gettext("If you came here by clicking on a link in a view, refresh that view.")
                    );
                  }
                });
            },

            loadItem: function (containerid, type, itemid, tab) {
                var Model, model, View, view, skipFetch;

                this._prepare(containerid, type, itemid);
                App.tree.currentView.activeNode = itemid;
                App.tree.currentView.highlightNodeById(itemid);
                model = App.instances.cache.get(itemid);
                if (_.isUndefined(model) || 
                    _.isUndefined(App.instances.tree.getTreeNode(itemid))) {
                    Model = this._typeClasses(type)[0];
                    model = new Model({ id: itemid });
                } else {
                    skipFetch = true;
                }
                View = this._typeClasses(type)[1];
                view = new View({ model: model });
                
                App.tree.currentView.activeNodeModel = model;
                App.instances.activeTab = tab;
                
                // Render the loader indicator
                App.main.show(App.instances.loaderView);
                model
                    .off("change")
                    .once("change", function () {
                        App.main.show(view);
                    });
                model
                    .off("policiesloaded")
                    .on("policiesloaded", function () {
                        if (_.has(view, "policiesList")) {
                            view.policiesList.render();
                        }
                    });

                if (skipFetch) {
                    // The object was cached
                    App.tree.currentView.closeAllExcept(model.get("path"));
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
                    that,
                    domain,
                    Model;

                if (_.isUndefined(resource)) {
                    Model = this._typeClasses(type)[0];
                    resource = new Model({ id: itemid });

                    that = this;
                    resource.fetch().done(function () {
                        domain = resource.get("path").split(',')[2];
                        domain = new App.OU.Models.OUModel({ id: domain });
                        domain.fetch().done(function () {
                            resource.set("isEditable", domain.get("master") === "gecos");
                            resource.set("master_policies", domain.get("master_policies"));
                            that.showPoliciesView(resource);
                        });
                    });
                    App.instances.cache.set(itemid, resource);
                    return;
                }

                this.showPoliciesView(resource);
            },

            showPoliciesView: function (resource) {
                App.main.show(App.instances.loaderView);

                var view = new App.Policies.Views.AllPoliciesWidget({
                    resource: resource
                });
                App.main.show(view);
            },

            loadPolicy: function (containerid, type, itemid, policyid) {
                var resource = App.instances.cache.get(itemid),
                    policy = App.instances.cache.get(policyid),
                    promise = $.Deferred(),
                    url = "ou/" + containerid + '/' + type + '/' + itemid;

                if (_.isUndefined(resource)) {
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

            search: function (keyword, parameters) {
                var params = parameters.split('&');
                var dparameters = []
                for (var p in params) {
                    var res = params[p].split("=");
                    dparameters[res[0]] = res[1];
                }

                if (! 'searchby' in dparameters) {
                    throw "Search require a 'search by' attribute";
                }
                if (! 'searchfilter' in dparameters) {
                    throw "Search require a 'search filter' attribute";
                }

                var lastTreeView = App.tree.currentView;
                if (!_.isUndefined(App.tree.currentView.treeView)) {
                    lastTreeView = App.tree.currentView.treeView;
                }

                var data = new App.Tree.Models.Search({ keyword: keyword, search_by: dparameters['searchby'], search_filter: dparameters['searchfilter']}),
                    view = new App.Tree.Views.SearchResults({
                        collection: data,
                        treeView: lastTreeView
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
        if (_.isUndefined(App.instances.myjob_statistics)) {
            App.instances.myjob_statistics = new App.Job.Models.MyJobStatistics();
            App.instances.myjob_statistics.fetch();
        }
        if (! (Backbone.history.getFragment() == 'logbook')) {
            $("#events-container").hide();
            App.events.show(new JobsView({collection: App.instances.job_collection}));
            App.eventsSummary.show(new JobsSummaryView({model: App.instances.myjob_statistics}));
        }
    });

    if (window.websocketsEnabled) {
        App.instances.message_manager = new MessageManager();
        App.instances.message_manager.bind('change', function (result) {
            App.instances.cache.drop(result.objectId);
            App.trigger('action_change', result);
        });
        App.instances.message_manager.bind('delete', function (result) {
            App.instances.cache.drop(result.objectId);
            App.trigger('action_delete', result);
        });
        App.instances.message_manager.bind('jobs', function (result) {
            if (result.username === window.GecosUtils.gecosUser.username) {
                App.instances.job_collection.fetch();
                App.instances.job_statistics.fetch();
                App.instances.myjob_statistics.fetch();
            }
        });
        App.instances.message_manager.bind('update_tree', function (result) {
            var path = result.path;
            App.instances.tree.loadFromPath(
                path,
                App.tree.currentView.activeNode
            );
        });
        App.instances.message_manager.bind('add_computer_to_user', function (result) {
            var user = App.instances.cache.get(result.user),
                computers;
            if (!_.isUndefined(user) && !_.isUndefined(user.get("computers"))) {
                computers = user.get("computers");
                computers.push(result.computer);
                user.set("computers", computers);
            }
        });
        App.instances.message_manager.bind('maintenance', function (result) {
            App.showAlert('warning', result.message);
        });
        
        App.instances.message_manager.bind('socktail', function(result) {
             $("#watchlog").append(result.logdata);
        });
        $(window).on('beforeunload', function () {
            App.instances.message_manager.silent_disconnect();
        });
        
    }
    App.instances.cut = undefined;
    
    /* Override the Backbone ajax function */
    Backbone.ajax = function() {
        var args = arguments;
        var errorFunc = args.error;
        args.error = function(xhr, textStatus, error){
            if (xhr.status === 403) {
                console.log('Forbidden access');
                forbidden_access();
            }
            else {
                errorFunc(xhr, textStatus, error);
            }
        };
        return Backbone.$.ajax.apply(Backbone.$, args);
    };
    
}(Backbone, jQuery, _, gettext, MessageManager));
