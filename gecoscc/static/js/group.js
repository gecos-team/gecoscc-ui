/*jslint browser: true, unparam: true, nomen: true, vars: false */
/*global App, GecosUtils, gettext */

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

App.module("Group.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.Group = Backbone.Model.extend({
        defaults: {
            name: "",
            groupmembers: [],
            nodemembers: []
        },

        url: function () {
            var url = "/api/groups/";
            if (this.has("id")) {
                url += this.get("id") + '/';
            }
            return url;
        },

        parse: function (response) {
            var result = _.clone(response);
            result.id = response._id;
            return result;
        }
    });

    Models.GroupCollection = Backbone.Collection.extend({
        model: Models.Group,

        url: function () {
            return "/api/groups/?pagesize=1000";
        },

        parse: function (response) {
            return response.groups;
        }
    });
});

App.module("Group.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.GroupRow = Marionette.ItemView.extend({
        template: "#groups-row-template",

        tagName: "tr",

        events: {
            "click button.edit-group": "edit",
            "click button.btn-danger": "deleteModel"
        },

        edit: function (evt) {
            evt.preventDefault();
            var id = this.$el.find("td").first().attr("id");
            App.instances.router.navigate("group/" + id, { trigger: true });
        },

        deleteModel: function (evt) {
            evt.preventDefault();
            var that = this;

            GecosUtils.confirmModal.find("button.btn-danger")
                .off("click")
                .on("click", function (evt) {
                    that.model.destroy({
                        success: function () {
                            App.instances.groups.fetch();
                        }
                    });
                    GecosUtils.confirmModal.modal("hide");
                });
            GecosUtils.confirmModal.modal("show");
        }
    });

    Views.GroupTable = Marionette.CompositeView.extend({
        template: "#groups-table-template",
        itemView: Views.GroupRow,
        itemViewContainer: "tbody",

        events: {
            "click button#add-group": "addGroup"
        },

        onRender: function () {
            /* Table initialisation */
            var $table = this.$el.find("table");

            if ($table.find("tr").length > 0) {
                $table.dataTable({
                    sDom: "<'row'<'col-md-8'l><'col-md-4'f>r>t<'row'<'col-md-7'i><'col-md-5'p>>",
                    sPaginationType: "bootstrap",
                    oLanguage: {
                        oAria: {
                            sSortAscending: gettext(": activate to sort column ascending"),
                            sSortDescending: gettext(": activate to sort column descending")
                        },
                        oPaginate: {
                            sFirst: gettext("First"),
                            sLast: gettext("Last"),
                            sPrevious: gettext("Next"),
                            sNext: gettext("Previous")
                        },
                        sEmptyTable: gettext("No data available in table"),
                        sInfo: gettext("Showing _START_ to _END_ of _TOTAL_ entries"),
                        sInfoEmpty: gettext("Showing 0 to 0 of 0 entries"),
                        sInfoFiltered: gettext("(filtered from _MAX_ total entries)"),
                        // sInfoPostFix: gettext("All records shown are derived from real information."),
                        // sInfoThousands: ",",
                        sLengthMenu: gettext("Show _MENU_ entries"),
                        sLoadingRecords: gettext("Loading..."),
                        sProcessing: gettext("Processing..."),
                        sSearch: gettext("Search:"),
                        // sUrl: "http://www.sprymedia.co.uk/dataTables/lang.txt",
                        sZeroRecords: gettext("No matching records found")
                    }
                });
            }
        },

        addGroup: function (evt) {
            evt.preventDefault();
            App.instances.router.navigate("group", { trigger: true });
        }
    });

    Views.GroupMembers = Marionette.ItemView.extend({
        template: "#groupmembers-template",

        initialize: function (options) {
            this.groupmembers = options.groupmembers;
        },

        serializeData: function () {
            return {
                groupmembers: _.pairs(this.groupmembers)
            };
        }
    });

    Views.NodeMembers = Marionette.ItemView.extend({
        template: "#nodemembers-template",

        initialize: function (options) {
            this.nodemembers = options.nodemembers;
        },

        serializeData: function () {
            return {
                nodemembers: _.pairs(this.nodemembers)
            };
        }
    });

    Views.GroupForm = Marionette.Layout.extend({
        template: "#groups-form-template",

        regions: {
            memberof: "#memberof",
            groupmembers: "#groupmembers",
            nodemembers: "#nodemembers"
        },

        events: {
            "click button#delete": "deleteModel",
            "click button#save": "save",
            "click button#goback": "go2table"
        },

        onRender: function () {
            var that = this,
                groups,
                widget,
                promise,
                aux;

            if (App.instances.groups && App.instances.groups.length > 0) {
                groups = App.instances.groups;
                promise = $.Deferred();
                promise.resolve();
            } else {
                groups = new App.Group.Models.GroupCollection();
                promise = groups.fetch();
            }

            widget = new Views.GroupWidget({
                collection: groups,
                checked: this.model.get("memberof"),
                unique: true
            });
            promise.done(function () {
                that.memberof.show(widget);
                that.memberof.$el.find("select").chosen();
            });

            aux = this.model.get("groupmembers").join(',');
            if (aux.length === 0) {
                aux = new Views.GroupMembers({ groupmembers: {} });
                this.groupmembers.show(aux);
            } else {
                $.ajax("/api/groups/?oids=" + aux).done(function (response) {
                    var items = response.groups,
                        groupmembers = {},
                        view;

                    _.each(items, function (g) {
                        groupmembers[g._id] = g.name;
                    });

                    view = new Views.GroupMembers({ groupmembers: groupmembers });
                    that.groupmembers.show(view);
                });
            }

            aux = this.model.get("nodemembers").join(',');
            if (aux.length === 0) {
                aux = new Views.NodeMembers({ nodemembers: {} });
                this.nodemembers.show(aux);
            } else {
                $.ajax("/api/nodes/?oids=" + aux).done(function (response) {
                    var items = response.nodes,
                        nodemembers = {},
                        view;

                    _.each(items, function (n) {
                        nodemembers[n._id] = n.name;
                    });

                    view = new Views.NodeMembers({ nodemembers: nodemembers });
                    that.nodemembers.show(view);
                });
            }
        },

        deleteModel: function (evt) {
            evt.preventDefault();
            var that = this;

            GecosUtils.confirmModal.find("button.btn-danger")
                .off("click")
                .on("click", function (evt) {
                    that.model.destroy({
                        success: function () {
                            App.instances.router.navigate("", { trigger: true });
                        }
                    });
                    GecosUtils.confirmModal.modal("hide");
                });
            GecosUtils.confirmModal.modal("show");
        },

        save: function (evt) {
            evt.preventDefault();
            var name, memberof, $button;

            name = this.$el.find("#name").val().trim();
            if (name.length === 0) {
                this.$el.find("#name").parent().addClass("has-error");
                return;
            }
            this.$el.find("#name").parent().removeClass("has-error");
            this.model.set("name", name);

            $button = $(evt.target);
            $button.tooltip({
                html: true,
                title: "<span class='fa fa-spin fa-spinner'></span> " + gettext("Saving") + "..."
            });
            $button.tooltip("show");

            memberof = this.memberof.currentView.getChecked();
            this.model.set("memberof", memberof);

            this.model.save()
                .done(function () {
                    $button.tooltip("destroy");
                    $button.tooltip({
                        html: true,
                        title: "<span class='fa fa-check'></span> " + gettext("Done")
                    });
                    $button.tooltip("show");
                    setTimeout(function () {
                        $button.tooltip("destroy");
                        App.instances.router.navigate("", { trigger: true });
                    }, 1500);
                })
                .fail(function () {
                    $button.tooltip("destroy");
                    $button.tooltip({
                        html: true,
                        title: "<span class='text-danger fa fa-exclamation-triangle'></span> " + gettext("Failure")
                    });
                    $button.tooltip("show");
                });
        },

        go2table: function (evt) {
            evt.preventDefault();
            App.instances.router.navigate("", { trigger: true });
        }
    });

    Views.GroupWidget = Marionette.ItemView.extend({
        template: "#groups-widget-template",

        unique: false,
        checked: undefined,

        initialize: function (options) {
            if (_.has(options, "unique")) {
                this.unique = options.unique;
            }
            if (_.has(options, "checked")) {
                this.checked = options.checked;
            }
        },

        ui: {
            filter: "input.group-filter"
        },

        events: {
            "keyup @ui.filter": "filterGroups",
            "click .group-filter-btn": "cleanFilter"
        },

        serializeData: function () {
            var data = {},
                aux,
                groups;

            if (this.collection) {
                if (this.unique) {
                    if (_.isUndefined(this.checked)) {
                        this.checked = "";
                    }
                } else if (_.isUndefined(this.checked)) {
                    this.checked = [];
                }

                aux = _.flatten([this.checked]);
                // Sort the groups, checked first
                groups = this.collection.toJSON();
                groups = _.sortBy(groups, function (g) {
                    return _.contains(aux, g.id) ? 0 : 1;
                });

                data = {
                    unique: this.unique,
                    items: groups,
                    checked: this.checked
                };
            }
            return data;
        },

        filterGroups: function (evt) {
            evt.preventDefault();
            var filter = this.ui.filter.val();

            this.$el.find("label.group").each(function (index, label) {
                var $label = $(label),
                    filterReady = filter.trim().toLowerCase(),
                    text = $label.text().trim().toLowerCase();
                if (filterReady.length === 0 || text.indexOf(filterReady) >= 0) {
                    $label.parent().show();
                } else {
                    $label.parent().hide();
                }
            });
        },

        cleanFilter: function (evt) {
            this.ui.filter.val("");
            this.filterGroups(evt);
            this.ui.filter.focus();
        },

        getChecked: function () {
            var result;
            if (this.unique) {
                result = this.$el.find("option:selected").val();
                if (result.length === 0) { return null; }
                return result;
            }
            return _.map(this.$el.find("input:checked"), function (item) {
                return $(item).attr("id");
            });
        }
    });
});
