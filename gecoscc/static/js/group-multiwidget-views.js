/*jslint browser: true, unparam: true, nomen: true, vars: false */
/*global App */

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

App.module("Group.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.MultiGroupWidget = Marionette.Layout.extend({
        template: "#groups-multi-widget-template",

        checked: undefined,

        initialize: function (options) {
            var that = this,
                checked = [];

            if (_.isArray(options.checked)) {
                checked = options.checked;
            }

            this.checked = new App.Group.Models.GroupCollection();

            _.each(checked, function (id) {
                var group = new App.Group.Models.GroupWithoutPoliciesModel({ id: id });
                group.fetch();
                that.checked.add(group);
            });

            this.collection = new App.Group.Models.PaginatedGroupCollection(null, { item_id: options.item_id, ou_id: options.ou_id });
            this.collection.goTo(1, {
                success: function () { that.render(); }
            });

            this.disabled = options.disabled;
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
                            var re = new RegExp(query.term + ".*");
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
                            }
                        });
                    }
                    lastTerm = query.term;
                }
            });

            if (this.disabled) {
                this.$el.find("input").prop("disabled", true);
            }
        },

        getChecked: function () {
            return _.rest($(".add-groups").select2('val'));
        }
    });
});
