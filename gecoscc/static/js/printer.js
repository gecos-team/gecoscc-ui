/*jslint browser: true, nomen: true, unparam: true, vars: false */
/*global App */

/*jslint browser: true, vars: false, nomen: true, unparam: true */
/*global App, gettext */

/*
* Copyright 2013, Junta de Andalucia
* http://www.juntadeandalucia.es/
*
* Authors:
*   Alberto Beiztegui <albertobeiz@gmail.com>
*   Alejandro Blanco <alejandro.b.e@gmail.com>
*   Pablo Caro <pcarorevuelta@gmail.com>
*
* All rights reserved - EUPL License V 1.1
* https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
*/

App.module("Printer.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.PrinterModel = App.Policies.Models.GecosResourceModel.extend({
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
            oppolicy: "default",
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
            "click button.refresh": "refresh",
            "click #cut": "cutModel"
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
            this.canMove();
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
                    if (that.model.get("isEditable")) {
                        that.setModelsSelect(that.$el.find('#manufacturer').attr('value'));
                    }
                }
            });

            if (!this.model.get("isEditable")) {
                this.$el.find("textarea,input,select").prop("disabled", true).prop("placeholder", '');
            }

            if (!_.isUndefined(this.model.id)) {
                this.$el.find("#name").attr('disabled', 'disabled');
            }
        },

        setModelsSelect: function (manufacturer) {
            var pagesize = 30,
                more,
                cachedData,
                cachedRequests = {},
                lastTerm = "",
                that = this;

            if (manufacturer !== '') {
                this.$el.find('#model').attr('disabled', false);
            }

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
                ppd_uri: "#ppd_uri",
                oppolicy: "#oppolicy"
            });
        }
    });
});
