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
        },

        add: function (models, options) {
            var that = this,
                promises = [];

            models = _.flatten([models]);
            _.each(models, function (model) {
                if (!(model instanceof Backbone.Model)) {
                    throw "Staging collection only works with Backbone models";
                }

                var id = model.get("id"),
                    promise = $.Deferred();

                that.promiseIndex[id] = promise;
                if (_.has(options, "arguments")) {
                    that.argumentsIndex[id] = options.arguments;
                }

                promises.push(promise);
                Backbone.Collection.prototype.add.call(that, model, options);
            });
            this.trigger("change");

            if (promises.length > 1) {
                return promises;
            }
            return promises[0];
        },

        remove: function (models, options) {
            var aux = _.flatten([models]),
                that = this;

            _.each(aux, function (model) {
                if (!(model instanceof Backbone.Model)) {
                    throw "Staging collection only works with Backbone models";
                }

                var id = model.get("id");
                delete that.promiseIndex[id];
                delete that.argumentsIndex[id];
                Backbone.Collection.prototype.remove.call(this, model, options);
                model.fetch();
            });

            this.trigger("change");
        },

        saveAll: function () {
            var that = this;

            this.each(function (model) {
                var id = model.get("id"),
                    args = [];

                if (_.has(that.argumentsIndex, id)) {
                    args = that.argumentsIndex[id];
                }

                Backbone.Model.prototype.save.apply(model, args)
                    .done(function (response) {
                        that.promiseIndex[id].resolve(response);
                    }).fail(function (response) {
                        that.promiseIndex[model.get("id")].reject(response);
                    }).always(function () {
                        that.remove(model);
                    });
            });
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
            "click button.btn-danger": "removeModel"
        },

        commitChanges: function (evt) {
            evt.preventDefault();
            this.collection.saveAll();
            this.$el.find("#staging-modal").modal("hide");
        },

        removeModel: function (evt) {
            evt.preventDefault();
            var $el = $(evt.target).parents("li").first(),
                model = this.collection.get($el.attr("id"));
            this.collection.remove(model);
        }
    });

    Views.CommitChangesButton = Marionette.ItemView.extend({
        tagName: "span",

        template: "#staging-button-template",

        serializeData: function () {
            return {
                changes: this.reportView.collection.length
            };
        },

        events: {
            "click button": "showReport"
        },

        initialize: function (options) {
            var that = this;

            this.reportView = new Views.Report({
                collection: App.instances.staging,
                el: "#staging-modal-viewport"
            });

            App.instances.staging.on("change", function () {
                that.render();
            });
        },

        showReport: function (evt) {
            evt.preventDefault();
            this.reportView.render();
            this.reportView.$el.find("#staging-modal").modal();
        }
    });
});
