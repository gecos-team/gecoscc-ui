/*jslint browser: true, unparam: true, nomen: true, vars: false */
/*global App */

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

App.module("Group.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.Members = Marionette.ItemView.extend({
        template: "#groups-members-template",

        initialize: function (options) {
            this.members = options.members;
            this.page = options.page;
            this.totalPages = options.totalPages;
        },

        serializeData: function () {
            return {
                members: _.pairs(this.members),
                page: this.page,
                totalPages: this.totalPages
            };
        }
    });

    Views.GroupForm = App.GecosFormItemView.extend({
        template: "#groups-form-template",
        tagName: "div",
        className: "col-sm-12",
        page: 0,
        perPage: 10,

        ui: {
            policies: "div#policies div.bootstrap-admin-panel-content"
        },

        events: {
            "click button#delete": "deleteModel",
            "click button#save": "save",
            "click button.refresh": "refresh",
            "click ul.pagination a": "goToPage",
            "click #cut": "cutModel"
        },

        policiesList: undefined,

        goToPage: function (evt) {
            evt.preventDefault();
            var $el = $(evt.target),
                list = $("#members").find("ul").first(),
                that = this;

            if ($el.parent().is(".disabled")) { return; }
            if ($el.is(".previous")) {
                this.page--;
            } else if ($el.is(".next")) {
                this.page++;
            } else {
                this.page = parseInt($el.text(), 10) - 1;
            }
            list.fadeOut("fast", function () {
                that.renderMembers("members", Views.Members);
            });
        },

        renderMembers: function (propName, View) {

            var startOid = this.perPage * this.page,
                oids = this.model.get(propName).slice(startOid, startOid + this.perPage).join(','),
                aux = {},
                that = this;

            if (oids.length === 0) {
                aux[propName] = {};
                aux = new View(aux);
                this.$el.find("#members").html(aux.render().el);
            } else {
                $.ajax({url: "/api/nodes/?oids=" + oids, 
                      statusCode: {
                        403: function() {
                          forbidden_access();
                        }
                      }
                }).done(function (response) {
                    var items = response.nodes,
                        members = {},
                        view;
                    _.each(items, function (el) {
                        members[el._id] = el.name;
                    });

                    aux[propName] = members;
                    aux.page = that.page;
                    aux.totalPages = that.totalPages;
                    view = new View(aux);

                    that.$el.find("#members").html(view.render().el);
                    $("#members").find("ul").first().hide().fadeIn("fast");
                });
            }
        },

        renderPolicies: function () {
            this.policiesList = new App.Policies.Views.PoliciesList({
                el: this.ui.policies[0],
                collection: this.model.get("policyCollection"),
                resource: this.model
            });

            this.policiesList.render();
        },

        onBeforeRender: function () {
            //Set domain dependent atributes
            var path = this.model.get("path");

            if (this.model.get("isEditable") !== undefined) { return; }

            if (path.split(',')[0] === "undefined") {
                this.model.set("isEditable", true);
            } else {
                this.getDomainAttrs();
            }
        },

        getDomainAttrs: function () {
            var that = this,
                domain = this.model.get("path").split(',')[2];

            domain = new App.OU.Models.OUModel({ id: domain });
            domain.fetch().done(function () {
                that.model.set("isEditable", domain.get("master") === "gecos");
                that.model.set("master_policies", domain.get("master_policies"));
                that.render();
            });
        },

        onRender: function () {
            this.canMove();

            if (!_.isUndefined(this.model.id)) {
                this.$el.find("#name").attr('disabled', 'disabled');
            }

            var that = this,
                groups,
                clone,
                promise;

            if (App.instances.groups && App.instances.groups.length > 0) {
                groups = App.instances.groups;
                promise = $.Deferred();
                promise.resolve();
            } else {
                groups = new App.Group.Models.GroupCollection();
                promise = groups.fetch();
            }

            clone = new App.Group.Models.GroupModel({
                id: this.model.get("id")
            });
            clone.fetch().done(function () {
                that.model.set("members", clone.get("members"));
                that.totalPages = that.model.get("members").length / that.perPage;
                that.totalPages = Math.floor(that.totalPages) + 1;
                that.renderMembers("members", Views.Members);
            });

            this.renderPolicies();
        },

        save: function (evt) {
            evt.preventDefault();

            this.saveModel($(evt.target), {
                name: "#name"
            });
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
