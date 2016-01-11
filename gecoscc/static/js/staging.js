/*jslint browser: true, vars: false, nomen: true, unparam: true */
/*global App, gettext */

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

App.module("Staging.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.ModelCollection = Backbone.Collection.extend({
        initialize: function (options) {
            this.promiseIndex = {};
            this.argumentsIndex = {};
            this.toDelete = [];
            this.toMove = [];
            this.toModify = [];
            this.listenTo(App, 'action_change', this.onAction);
            this.listenTo(App, 'action_delete', this.onAction);
            this.token =  this.createToken();
        },

        createToken: function () {
            return Math.random().toString(36).substr(2);
        },

        onAction: function (result) {
            var model = this.get(result.objectId);

            if (!_.isUndefined(model)) {
                this.dropModel(model);
                if (this.token !== result.token) {
                    App.showChangeAlert({
                        action: result.action,
                        nodeName: model.get("name"),
                        id: model.get("id"),
                        user: result.user
                    });
                }
            }
        },

        getArgumentIndexId: function (model) {
            return model.get("id") || (model.get("type") + model.get("name"));
        },

        add: function (models, options) {
            var that = this,
                promises = [];

            options = options || {};

            models = _.flatten([models]);
            _.each(models, function (model) {
                if (!(model instanceof Backbone.Model)) {
                    throw "Staging collection only works with Backbone models";
                }

                var id = that.getArgumentIndexId(model),
                    promise = $.Deferred();

                promises.push(promise);

                if (_.contains(that.toDelete, id)) {
                    App.showAlert(
                        "error",
                        gettext("Resource marked for deletion."),
                        gettext("Your latest changes in this resource will be ignored.")
                    );
                    promise.reject("avoid alert");
                } else {
                    that.promiseIndex[id] = promise;
                    if (_.has(options, "arguments")) {
                        that.argumentsIndex[id] = options.arguments;
                    }
                    if (options.destroy) {
                        that.toDelete.push(id);
                    }

                    Backbone.Collection.prototype.add.call(that, model, options);
                }
            });
            this.trigger("change");

            if (promises.length > 1) {
                return promises;
            }
            return promises[0];
        },

        dropModel: function (models, options) {
            var aux = _.flatten([models]),
                that = this;

            options = options || {};

            _.each(aux, function (model) {
                if (!(model instanceof Backbone.Model)) {
                    throw "Staging collection only works with Backbone models";
                }

                var id = that.getArgumentIndexId(model);
                delete that.promiseIndex[id];
                delete that.argumentsIndex[id];
                that.toDelete = _.reject(that.toDelete, function (objId) {
                    return objId === id;
                });
                that.toMove = _.reject(that.toMove, function (objId) {
                    return objId[0] === id;
                });
                that.toModify = _.reject(that.toModify, function (objId) {
                    return objId === id;
                });
                that.remove(model, options); // Actually remove it from the collection

                if (!options.avoidRestore) {
                    model.fetch().done(function () {
                        App.instances.tree.trigger("change");
                    });
                }
            });

            this.trigger("change");
        },

        saveAll: function () {
            var that = this,
                promises = [];

            _.chain(this.models).clone().each(function (model) {
                var id = that.getArgumentIndexId(model),
                    action = Backbone.Model.prototype.save,
                    args = [],
                    promise;

                if (_.has(that.argumentsIndex, id)) {
                    args = that.argumentsIndex[id];
                }
                if (_.contains(that.toDelete, id)) {
                    action = Backbone.Model.prototype.destroy;
                }

                promise = action.apply(model, args);
                promises.push(promise);
                promise
                    .done(function (response) {
                        if (!_.isUndefined(that.promiseIndex[id])) { that.promiseIndex[id].resolve(response); }
                    }).fail(function (response) {
                        that.promiseIndex[id].reject(response);
                    }).always(function () {
                        that.dropModel(model, { avoidRestore: true });
                    });
            });

            return promises;
        },

        isPendingOfDeletion: function (id) {
            return _.contains(this.toDelete, id);
        }
    });
});

App.module("Staging.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    App.addInitializer(function () {
        var view;
        App.instances.staging = new App.Staging.Models.ModelCollection();
        view = new Views.CommitChangesButton({ el: "#commit-changes" });
        view.render();
    });

    Views.Report = Marionette.ItemView.extend({
        template: "#staging-report-template",

        events: {
            "click button.btn-primary": "commitChanges",
            "click button.discard": "removeModel",
            "click button.btn-default": "updateTree"
        },

        initialize: function (options) {
            this.commitChangesButtonView = options.commitChangesButtonView;
        },

        serializeData: function () {
            return {
                items: this.collection.toJSON(),
                deletions: this.collection.toDelete,
                moves: this.collection.toMove,
                modified: this.collection.toModify
            };
        },

        commitChanges: function (evt) {
            evt.preventDefault();
            var promises = this.collection.saveAll();
            this.commitChangesButtonView.showInProgress(promises);
            this.$el.find("#staging-modal").modal("hide");
        },

        removeModel: function (evt) {
            evt.preventDefault();
            var $el = $(evt.target).parents("li").first(),
                model = this.collection.get($el.attr("id")) || this.collection.where({name: $el.attr("name")});
            $el.hide();
            this.collection.dropModel(model);
            if (this.collection.length === 0) {
                App.instances.tree.trigger("change");
                this.$el.find("#staging-modal").modal("hide");
            }
        },

        updateTree: function () {
            App.instances.tree.trigger("change");
        }
    });

    Views.CommitChangesButton = Marionette.ItemView.extend({
        tagName: "span",

        template: "#staging-button-template",

        serializeData: function () {
            return {
                changes: this.reportView.collection.length,
                inProgress: this.inProgress
            };
        },

        events: {
            "click button": "showReport"
        },

        initialize: function (options) {
            var that = this;

            this.reportView = new Views.Report({
                collection: App.instances.staging,
                el: "#staging-modal-viewport",
                commitChangesButtonView: this
            });
            this.inProgress = false;

            App.instances.staging.on("change", function () {
                that.render();
            });

            window.onbeforeunload = function () {
                if (App.instances.staging.length > 0) {
                    return 'You have made some changes which you might want to save.';
                }
            };
        },

        showReport: function (evt) {
            evt.preventDefault();
            this.reportView.render();
            this.reportView.$el.find("#staging-modal").modal();
        },

        showInProgress: function (promises) {
            var that = this;
            this.inProgress = true;
            $.when.apply($, promises)
                .done(function () {
                    if(typeof App.instances.refresh == 'undefined'){
                        App.instances.refresh = {};
                    }

                    App.tree.currentView.activeNode = null;
                    App.instances.tree.trigger("change");
                    App.instances.router.navigate("", { trigger: true });

                    _.each(App.instances.refresh,function(value,key){
                        App.instances.refresh[key] = true;
                    });

                }).always(function () {
                    that.inProgress = false;
                    that.render();
                });
        }
    });
});
