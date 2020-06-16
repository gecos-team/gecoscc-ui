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

    Views.MultiGroupWidget = Marionette.Layout.extend({
        template: "#groups-multi-widget-template",

        checked: undefined,
        notVisible: [],

        initialize: function (options) {
            var that = this,
                checked = [];
            this.notVisible = [];

            if (_.isArray(options.checked)) {
                checked = options.checked;
            }

            this.checked = new App.Group.Models.GroupCollection();

            _.each(checked, function (id) {
                var group = new App.Group.Models.GroupWithoutPoliciesModel({ id: id });
                group.fetch().error(function () {
                    that.notVisible.push(id);
                }).always(function () {
                    that.render();
                });
                that.checked.add(group);
            });

            this.collection = new App.Group.Models.PaginatedGroupCollection(null, { item_id: options.item_id, ou_id: options.ou_id });
            this.collection.goTo(1, {
                success: function () { that.render(); }
            });

            this.disabled = options.disabled;
        },

        onBeforeRender: function () {
            var that = this;
            _.each(this.notVisible, function (g) {
                that.checked.remove(g);
            });
        },

        onRender: function () {
            var that = this,
                pagesize = 30,
                more,
                cachedData,
                cachedRequests = {},
                lastTerm = "";

            this.$el.find(".add-groups").select2({
                multiple: true,
                initSelection: function (element, callback) {
                    var data = [];
                    _.each(that.checked.models, function (g) {
                        data.push({id: g.id, text: g.get("name")});
                    });
                    callback(data);
                },
                query: function (query) {
                    if (lastTerm.length < query.term.length && !more) {
                        cachedData = _.filter(cachedData, function (d) {
                            var re = new RegExp(query.term + ".*", "i");
                            return re.test(d.text);
                        });
                        cachedRequests[query.term] = _.clone(cachedData);
                        query.callback({results: cachedData});
                    } else if (cachedRequests[query.term]) {
                        query.callback({results: cachedRequests[query.term]});
                    } else {
                        $.ajax({
                            url: "/api/groups/",
                            dataType: 'json',
                            id : function (node) {
                                return node._id;
                            },
                            data:  {
                                item_id: that.options.item_id,
                                ou_id: that.options.ou_id,
                                iname: query.term,
                                page: query.page,
                                pagesize: pagesize

                            },
                            type: 'GET',
                            success: function (data) {
                                var nodes = data.nodes.map(function (n) {
                                    return {
                                        text: n.name,
                                        value: n._id,
                                        id: n._id
                                    };
                                });
                                more = data.nodes.length >= pagesize;
                                if (data.page === 1) {
                                    cachedData = nodes;
                                } else {
                                    cachedData = _.union(cachedData, nodes);
                                }

                                query.callback({results: nodes, more: more});
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
                    }
                    lastTerm = query.term;
                }
            });

            if (this.notVisible.length > 0) {
                that.$el.find(".groups-warning-message").removeClass("hidden");
            }

            if (this.disabled) {
                this.$el.find("input").prop("disabled", true);
            }
        },

        serializeData: function () {
            return {
                name: this.options.name + " "
            };
        },

        getChecked: function () {
            return _.union(_.rest($(".add-groups").select2('val')), this.notVisible);
        }
    });
});
