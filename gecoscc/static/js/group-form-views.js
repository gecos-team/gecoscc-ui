/*jslint browser: true, unparam: true, nomen: true, vars: false */
/*global App */

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

App.module("Group.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.Members = Marionette.ItemView.extend({
        template: "#groups-members-template",

        initialize: function (options) {
            this.members = options.members;
        },

        serializeData: function () {
            return {
                members: _.pairs(this.members)
            };
        }
    });

    Views.GroupForm = Marionette.Layout.extend({
        template: "#groups-form-template",
        tagName: "div",
        className: "col-sm-12",

        regions: {
            memberof: "#memberof",
            members: "#members"
        },

        events: {
            "click button#delete": "deleteModel",
            "click button#save": "save",
            "click button#goback": "go2table"
        },

        helperView: undefined,

        initialize: function (options) {
            this.helperView = new App.GecosFormItemView({
                model: options.model,
                el: this.el
            });
            this.helperView.resourceType = "group";
        },

        renderMembers: function (propName, View) {
            var oids = this.model.get(propName).join(','),
                aux = {},
                that = this;

            if (oids.length === 0) {
                aux[propName] = {};
                aux = new View(aux);
                this[propName].show(aux);
            } else {
                $.ajax("/api/nodes/?oids=" + oids).done(function (response) {
                    var items = response.nodes,
                        members = {},
                        view;

                    _.each(items, function (el) {
                        members[el._id] = el.name;
                    });

                    aux[propName] = members;
                    view = new View(aux);
                    that[propName].show(view);
                });
            }
        },

        onRender: function () {
            var that = this,
                memberof = this.model.get("memberof"),
                groups,
                widget,
                promise;

            if (App.instances.groups && App.instances.groups.length > 0) {
                groups = App.instances.groups;
                promise = $.Deferred();
                promise.resolve();
            } else {
                groups = new App.Group.Models.GroupCollection();
                promise = groups.fetch();
            }

            memberof = memberof.length > 0 ? memberof[0] : "";
            widget = new Views.GroupWidget({
                collection: groups,
                checked: memberof
            });
            promise.done(function () {
                that.memberof.show(widget);
            });

            this.renderMembers("members", Views.Members);
        },

        deleteModel: function (evt) {
            this.helperView.deleteModel(evt);
        },

        save: function (evt) {
            evt.preventDefault();
            this.helperView.saveModel($(evt.target), {
                memberof: _.bind(this.memberof.currentView.getChecked, this),
                name: "#name"
            });
        },

        go2table: function (evt) {
            evt.preventDefault();
            App.instances.router.navigate("", { trigger: true });
        }
    });

    Views.GroupWidget = Marionette.ItemView.extend({
        template: "#groups-widget-template",

        checked: undefined,

        initialize: function (options) {
            if (_.has(options, "checked")) {
                this.checked = options.checked;
            }
        },

        serializeData: function () {
            var data = {},
                that = this,
                groups;

            if (this.collection) {
                if (this.unique) {
                    if (_.isUndefined(this.checked)) {
                        this.checked = "";
                    }
                }

                // Sort the groups, checked first
                groups = this.collection.toJSON();
                groups = _.sortBy(groups, function (g) {
                    return that.checked === g.id ? 0 : 1;
                });

                data = {
                    items: groups,
                    checked: this.checked
                };
            }
            return data;
        },

        onRender: function () {
            this.$el.find("select").chosen();
        },

        getChecked: function () {
            var result = this.$el.find("option:selected").val();
            if (result.length === 0) { return null; }
            return result;
        }
    });
});
