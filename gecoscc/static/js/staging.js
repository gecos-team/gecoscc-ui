/*jslint browser: true, vars: false, nomen: true, unparam: true */
/*global App, gettext */

// Copyright 2014 Junta de Andalucia
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

App.module("Staging.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.ModelCollection = Backbone.Collection.extend({
        initialize: function (options) {
            this.promiseIndex = {};
            this.argumentsIndex = {};
            this.toDelete = [];
            this.listenTo(App, 'action_change', this.onAction);
            this.listenTo(App, 'action_delete', this.onAction);
        },

        onAction: function (obj) {
            var model = this.get(obj._id);
            if (!_.isUndefined(model)) {
                this.dropModel(model);
            }
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

                var id = model.get("id"),
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

                var id = model.get("id");
                delete that.promiseIndex[id];
                delete that.argumentsIndex[id];
                that.toDelete = _.reject(that.toDelete, function (objId) {
                    return objId === id;
                });
                that.remove(model, options); // Actually remove it from the collection

                if (!options.avoidRestore) {
                    model.fetch();
                    // TODO update node in tree
                }
            });

            this.trigger("change");
        },

        saveAll: function () {
            var that = this,
                promises = [];

            this.each(function (model) {
                var id = model.get("id"),
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
                        that.promiseIndex[id].resolve(response);
                    }).fail(function (response) {
                        that.promiseIndex[model.get("id")].reject(response);
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
            "click button.discard": "removeModel"
        },

        initialize: function (options) {
            this.commitChangesButtonView = options.commitChangesButtonView;
        },

        serializeData: function () {
            return {
                items: this.collection.toJSON(),
                deletions: this.collection.toDelete
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
                model = this.collection.get($el.attr("id"));

            $el.hide();
            this.collection.dropModel(model);
            if (this.collection.length === 0) {
                this.$el.find("#staging-modal").modal("hide");
            }
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
            
            
            window.onbeforeunload = function() {
                if(App.instances.staging.length > 0){
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
                    App.tree.currentView.activeNode = null;
                    App.instances.router.navigate("", { trigger: true });
                }).always(function () {
                    that.inProgress = false;
                    that.render();
                });
        }
    });
});
