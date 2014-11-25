/*jslint browser: true, nomen: true, unparam: true, vars: false */
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

App.module("Printer.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.PrinterModel = App.GecosResourceModel.extend({
        resourceType: "printer",

        defaults: {
            type: "printer",
            lock: false,
            source: "gecos",
            printtype: "laser",
            manufacturer: "",
            model: "",
            serial: "",
            registry: "",
            name: "",
            description: "",
            location: "",
            connection: "network",
            uri: "",
            ppd_uri: "",
            isEditable: undefined
        }
    });
});

App.module("Printer.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.PrinterForm = App.GecosFormItemView.extend({
        template: "#printer-template",
        tagName: "div",
        className: "col-sm-12",
        modelsAPIUrl: "/api/printer_models/",

        events: {
            "click #submit": "saveForm",
            "click #delete": "deleteModel",
            "change input": "validate",
            "click button.refresh": "refresh"
        },

        onBeforeRender: function () {
            var path = this.model.get("path"),
                domain,
                that;

            if (this.model.get("isEditable") !== undefined) { return; }
            domain = path.split(',')[2];

            if (path.split(',')[0] === "undefined") {
                this.model.set("isEditable", true);
            } else {
                that = this;
                domain = new App.OU.Models.OUModel({ id: domain });
                domain.fetch().done(function () {
                    that.model.set("isEditable", domain.get("master") === "gecos");
                    that.render();
                });
            }
        },

        onRender: function () {
            var promise = $.get(this.modelsAPIUrl + "?manufacturers_list=true"),
                that = this;

            promise.done(function (res) {
                if (!_.isUndefined(res.printer_models)) {
                    var data = _.map(res.printer_models, function (p) {
                            return {id: p.manufacturer, text: p.manufacturer};
                        });
                    that.$el.find('#manufacturer').select2({
                        data: data
                    }).on("change", function (man) {
                        that.$el.find('#model').attr('value', '');
                        that.setModelsSelect(man.val);
                    });
                    that.setModelsSelect(that.$el.find('#manufacturer').attr('value'));
                }
            });
        },

        setModelsSelect: function (manufacturer) {
            var pagesize = 30,
                more,
                cachedData,
                cachedRequests = {},
                lastTerm = "",
                that = this;
            this.$el.find('#model').select2({
                initSelection : function (element, callback) {
                    var model = that.$el.find('#model').attr('value'),
                        data = {id: model, text: model};
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
                            url: that.modelsAPIUrl,
                            dataType: 'json',
                            id : function (node) {
                                return node.model;
                            },
                            data:  {
                                manufacturer: manufacturer,
                                imodel: query.term,
                                page: query.page,
                                pagesize: pagesize
                            },
                            type: 'GET',
                            success: function (data) {
                                var models = data.printer_models.map(function (n) {
                                    return {
                                        text: n.model,
                                        value: n.model,
                                        id: n.model
                                    };
                                });
                                more = data.printer_models.length >= pagesize;
                                if (data.page === 1) {
                                    cachedData = models;
                                } else {
                                    cachedData = _.union(cachedData, models);
                                }

                                query.callback({results: models, more: more});
                            }
                        });
                    }
                    lastTerm = query.term;
                }
            });
        },

        saveForm: function (evt) {
            evt.preventDefault();

            this.saveModel($(evt.target), {
                printtype: "#type option:selected",
                manufacturer: "#manufacturer",
                model: "#model",
                serial: "#serial",
                registry: "#registry",
                name: "#name",
                description: "#description",
                location: "#location",
                connection: "#connection option:selected",
                uri: "#uri",
                ppd_uri: "#ppd_uri"
            });
        }
    });
});
