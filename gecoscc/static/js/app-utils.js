/*jslint browser: true, vars: false, nomen: true */
/*global App, Backbone, jQuery, _, gettext, interpolate */

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

(function (App, Backbone, $, _) {
    "use strict";

    var AlertView, ChangesAlertView, numericRegex, emailRegex, ipRegex, urlRegex, applyRegex, urlExtendRegex;

    /*
    * Regular expressions taken from:
    *
    * validate.js 1.3
    * Copyright (c) 2011 Rick Harrison, http://rickharrison.me
    * validate.js is open sourced under the MIT license.
    * Portions of validate.js are inspired by CodeIgniter.
    * http://rickharrison.github.com/validate.js
    */

    numericRegex = /^[0-9]+$/;
//     integerRegex = /^\-?[0-9]+$/;
//     decimalRegex = /^\-?[0-9]*\.?[0-9]+$/;
    emailRegex = /^[a-zA-Z0-9.!#$%&amp;'*+\-\/=?\^_`{|}~\-]+@[a-zA-Z0-9\-]+(?:\.[a-zA-Z0-9\-]+)*$/;
//         alphaRegex = /^[a-z]+$/i,
//         alphaNumericRegex = /^[a-z0-9]+$/i,
//         alphaDashRegex = /^[a-z0-9_\-]+$/i,
//         naturalRegex = /^[0-9]+$/i,
//         naturalNoZeroRegex = /^[1-9][0-9]*$/i,
    ipRegex = /^((25[0-5]|2[0-4][0-9]|1[0-9]{2}|[0-9]{1,2})\.){3}(25[0-5]|2[0-4][0-9]|1[0-9]{2}|[0-9]{1,2})$/;
//         base64Regex = /[^a-zA-Z0-9\/\+=]/i,
//         numericDashRegex = /^[\d\-\s]+$/,
    urlRegex = /^((http|https):\/\/(\w+:{0,1}\w*@)?(\S+)|)(:[0-9]+)?(\/|\/([\w#!:.?+=&%@!\-\/]))?$/;
    urlExtendRegex = /^(https?|ftp|file):\/\/[\-A-Za-z0-9+&@#\/%?=~_|!:,.;]+[\-A-Za-z0-9+&@#\/%=~_|]$/;

    /*
    * End - validate.js
    */

    applyRegex = function (regex, $el) {
        var valid = true;
        if (regex.test($el.val().trim())) {
            $el.parent().removeClass("has-error");
        } else {
            $el.parent().addClass("has-error");
            valid = false;
        }
        return valid;
    };

    // Custom models and views, for reusing code between resources

    App.GecosResourceModel = Backbone.Model.extend({
        url: function () {
            var url = "/api/" + this.resourceType + "s/";
            if (this.has("id")) {
                url += this.get("id") + '/';
            }
            return url;
        },

        parse: function (response) {
            var result = _.clone(response);
            result.id = response._id;
            return result;
        },

        saveWithToken: function () {
            var that = this;
            return this.save({}, { url: that.url() + "?token=" + App.instances.staging.token });
        },

        save: function () {
            return App.instances.staging.add(this, { arguments: arguments });
        },

        destroy: function () {
            return App.instances.staging.add(this, {
                arguments: arguments,
                destroy: true
            });
        },

        _showErrorMessage: function (response) {
            if ($(".server-errors").length === 0) {
                App.showAlert(
                    "error server-errors",
                    gettext("Applying changes has failed."),
                    this._errorMessage(response)
                );
            } else {
                this._addErrorMessage(response);
            }
        },

        _errorMessage: function (response) {
            var message = [
                gettext("Something went wrong, please check errors and try again.") + '</br>'
            ],
                json = response.responseJSON,
                that = this;

            if (_.has(response, "status") && !_.contains([400, 404], response.status) && _.has(response, "statusText")) {
                message.push("- " + gettext("Status") + response.status +
                             ": " + response.statusText + '</br>');
            }

            if (!_.isUndefined(json) && _.has(json, "errors")) {
                _.each(json.errors, function (error) {
                    message.push("&#8226; " + gettext("Error in node: ") + '<strong>' + that.get("name") + '</strong>' +
                                    " - " + gettext("Server response: ") + error.description);
                });
            }

            if (_.has(response, "status") && response.status === 404) {
                message.push("&#8226; " + gettext("Error in node: ") + '<strong>' + that.get("name") + '</strong>' +
                                    " - " + gettext("This node has been deleted by another administrator."));
                App.instances.tree.loadFromPath(that.get("path"));
            }

            return message.join(' ');
        },

        _addErrorMessage: function (response) {
            var json = response.responseJSON,
                that = this;

            if (!_.isUndefined(json) && _.has(json, "errors")) {
                _.each(json.errors, function (error) {
                    $(".server-errors").append('<br/>&#8226; ' + gettext("Error in node: ") + '<strong>' + that.get("name") + '</strong> - ' + gettext("Server response: ") + error.description);
                });
            }

            if (_.has(response, "status") && response.status === 404) {
                $(".server-errors").append("&#8226; " + gettext("Error in node: ") + '<strong>' + that.get("name") + '</strong>' +
                                    " - " + gettext("This node has been deleted by another administrator."));
                App.instances.tree.loadFromPath(that.get("path"));
            }
        }
    });

    App.GecosFormItemView = Backbone.Marionette.ItemView.extend({
        // a resourceType property should be declared by models that use
        // this view for edition, example:
        //
        // resourceType: "user",

        onRender: function () {
            if (!_.isUndefined(this.model.id)) {
                this.$el.find("#name").attr('disabled', 'disabled');
            }
        },

        initialize: function () {
            this.listenTo(App, 'action_change', this.onActionChange);
            this.listenTo(App, 'action_delete', this.onActionDelete);
        },

        onActionChange: function (obj) {
            if (App.instances.staging.token !== obj.token && this.model.id === obj.objectId) {
                App.showAlert(
                    "error",
                    gettext("Object changed."),
                    gettext("Someone has changed this object while you were working on it, please reload before applying any changes.")
                );
                this.disableSave();
            }
        },

        onActionDelete: function (obj) {
            if (App.instances.staging.token !== obj.token && this.model.id === obj.objectId) {
                App.showAlert(
                    "error",
                    gettext("Object deleted."),
                    gettext("Someone has deleted this object while you were working on it")
                );
                this.disableSave();
            }
        },


        disableSave: function () {
            var $save = this.$el.find("#submit");
            $save.attr('disabled', 'disabled');
        },

        refresh: function (evt) {
            var that = this;
            if (!_.isUndefined(evt)) {
                evt.preventDefault();
            }
            App.instances.staging.dropModel(this.model);
            $("#alerts-area .alert").slideUp('fast', function () {
                $(this).find("button.close").click();
            });
            $(this.el).fadeOut(function () {
                that.groupsWidget = undefined;
                that.policiesList = undefined;
                that.model.fetch().done(function () {
                    that.render();
                }).done(function () {
                    $(that.el).fadeIn();
                });
            });
        },

        validate: function (evt) {
            var valid = true,
                $elems;

            if (evt) {
                $elems = [evt.target];
            } else {
                $elems = this.$el.find("input");
            }

            _.each($elems, function (el) {
                var $el = $(el);

                if ($el.is("[required]")) {
                    if ($el.val().trim() === "") {
                        $el.parent().addClass("has-error");
                        valid = false;
                    } else {
                        $el.parent().removeClass("has-error");
                    }
                } else if ($el.val().trim() === "") {
                    // Not required and empty, avoid more validation
                    return;
                }

                if ($el.is("[type=email]")) {
                    valid = valid && applyRegex(emailRegex, $el);
                } else if ($el.is("[type=number]")) {
                    valid = valid && applyRegex(numericRegex, $el);
                } else if ($el.is("[type=url]")) {
                    valid = valid && applyRegex(urlRegex, $el);
                } else if ($el.is("[type=tel]")) {
                    valid = valid && applyRegex(numericRegex, $el);
                } else if ($el.is(".ip")) {
                    valid = valid && applyRegex(ipRegex, $el);
                } else if ($el.is(".urlExtend")) {
                    valid = valid && applyRegex(urlExtendRegex, $el);
                }
            });

            return valid;
        },

        customValidate: function () {
            // To be overwritten
            return true;
        },

        _setPropInModel: function (prop, key) {
            var value;

            if (_.isString(key)) {
                value = this.$el.find(key).val().trim();
            } else if (_.isFunction(key)) {
                value = key();
            } else {
                value = key;
            }

            if (prop === "memberof") {
                // Uncache old and new referenced nodes
                _.each([this.model.get("memberof"), value], function (ids) {
                    if (!_.isArray(ids)) { ids = [ids]; }
                    _.each(ids, function (id) {
                        App.instances.cache.drop(id);
                    });
                });
            }

            this.model.set(prop, value, { silent: true });
        },

        _showSavingProcess: function ($button, phase) {
            var text;

            if (phase === "progress") {
                $button.attr("disabled", "disabled");
                $button.html("<span class='fa fa-spin fa-spinner'></span> " +
                             gettext("Staging") + "...");
                return;
            }

            text = phase === "saved" ? gettext("Save") : gettext("Delete");
            $button.html("<span class='fa fa-check'></span> " + gettext("Done"));
            setTimeout(function () {
                $button.html(text);
                $button.attr("disabled", false);
            }, 2000);
        },

        saveModel: function ($button, mapping) {
            var that = this,
                promise = $.Deferred(),
                isNew = this.model.isNew();

            if (!(this.validate() && this.customValidate())) {
                App.showAlert(
                    "error",
                    gettext("Invalid data."),
                    gettext("Please, fix the errors in the fields below and try again.")
                );
                promise.reject();
                return promise;
            }
            if (App.alerts) {
                App.alerts.close();
            }

            this._showSavingProcess($button, "progress");
            _.each(_.pairs(mapping), function (relation) {
                that._setPropInModel(relation[0], relation[1]);
            });

            promise = this.model.saveWithToken();
            setTimeout(function () {
                that._showSavingProcess($button, "saved");
                if (!isNew) {
                    App.instances.staging.toModify.push(that.model.get("id"));
                }
                App.instances.tree.trigger("change");
            }, 100);

            promise.done(function () {
                if (isNew) {
                    App.instances.tree.loadFromPath(
                        that.model.get("path"),
                        that.model.get("id")
                    );
                } else {
                    App.instances.tree.updateNodeById(that.model.get("id"));
                }
            });
            promise.fail(function (response) {
                that.model._showErrorMessage(response);
            });

            return promise;
        },

        deleteModel: function (evt) {
            evt.preventDefault();
            var that = this,
                $button = $(evt.target),
                promise;

            this._showSavingProcess($button, "progress");
            promise = this.model.destroy({ url: that.model.url() + "?token=" + App.instances.staging.token });
            setTimeout(function () {
                that._showSavingProcess($button, "success");
                App.instances.tree.trigger("change");
            }, 1000);

            promise.done(function () {
                App.instances.tree.loadFromPath(that.model.get("path"));
            });
            promise.fail(function (response) {
                that.model._showErrorMessage(response);
            });
        },

        cutModel: function (evt) {
            var that = this;
            var $button = $('#cut');
            evt.preventDefault(); 
            var cutModel = function(){
                var $button = $(evt.target);
                $button.attr("disabled", "disabled");
                App.instances.cut = that.model;
                App.instances.tree.trigger("change");

                setTimeout(function () {
                    $button.attr("disabled", false);
                }, 2000);
            };

            if($button.hasClass('admin') && !App.instances.noMaintenance[this.model.get('id')]){
                var $modal = $('#maintenance-modal');
                $modal.modal('show');
                $('#set-maintenance').click(function(){
                    cutModel();
                    $modal.modal('hide');
                });
            }else{
                 cutModel();
            }



        },
        canMove: function(){
            var $button = this.$('#cut');
            if(typeof App.instances.noMaintenance == 'undefined'){
                App.instances.noMaintenance = [];
            }
            if(typeof App.instances.refresh == 'undefined'){
                App.instances.refresh = {};
            }
            var disable = function(){
                    $button.removeClass('btn-warning');
                    $button.addClass('btn-group');
                    $button.removeAttr('id');
                    $button.unbind('click');
                    $button.css('margin-right','5px');
                    $button.click(function(e){
                        e.preventDefault();
                        App.showAlert('warning',gettext('Only the super admin can cut this object'));
                    });
            };

            if(this.model.get('type')=='group'){
                if($button.hasClass('admin')==false && this.model.get('members').length != 0){
                    disable();
                    App.instances.noMaintenance[this.model.get('id')] = false;
                }
                if($button.hasClass('admin')==true && this.model.get('members').length == 0){
                    App.instances.noMaintenance[this.model.get('id')] = true;
                }
            }
            if(this.model.get('type')=='storage' || this.model.get('type')=='printer' || this.model.get('type')=='repository'){
                if(App.instances.refresh[this.model.get('id')]){
                    this.refresh();
                    delete App.instances.refresh[this.model.get('id')];
                }

                if($button.hasClass('admin')==false && this.model.get('is_assigned') == true){
                    disable();
                    App.instances.noMaintenance[this.model.get('id')] = false;
                }
                if($button.hasClass('admin')==true && this.model.get('is_assigned') == false){
                    App.instances.noMaintenance[this.model.get('id')] = true;
                }
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
        }
    });

    AlertView = Backbone.Marionette.ItemView.extend({
        template: "#alert-template",
        tagName: "div",
        className: "col-sm-12",

        data: {
            cssClass: "info",
            strongText: "",
            regularText: ""
        },

        serializeData: function () {
            return this.data;
        },

        initialize: function (options) {
            if (_.has(options, "type")) {
                this.data.cssClass = options.type;
            }
            if (_.has(options, "bold")) {
                this.data.strongText = options.bold;
            }
            if (_.has(options, "text")) {
                this.data.regularText = options.text;
            }
        },

        onRender: function () {
            var $el = this.$el;
            $('html, body').animate({
                scrollTop: $el.offset().top
            }, 200);
        }
    });

    App.showAlert = function (type, bold, text) {
        var view;

        type = type.replace("error", "danger");
        view = new AlertView({
            type: type,
            bold: bold,
            text: text
        });
        App.alerts.show(view);
    };

    ChangesAlertView = Backbone.Marionette.ItemView.extend({
        template: "#change-alert-template",
        tagName: "div",

        events: {
            "click a": "close",
            "click btn-default": "close"
        },

        data: {
            nodes: []
        },

        close: function () {
            this.$el.find(".modal").modal("hide");
        },

        serializeData: function () {
            return this.data;
        },

        initialize: function (options) {
            this.data.nodes.push.apply(this.data.nodes, options.node);
        },

        onRender: function () {
            var $el = this.$el,
                that = this;
            $el.find(".modal").on('hidden.bs.modal', function () {
                $el.find(".modal").remove();
                that.data.nodes = [];
            });
        }
    });

    App.showChangeAlert = function (data) {
        var $el = $("#staging-modal-changes"),
            view;

        if ($el.find(".modal").length === 0) {
            App.instances.changes = new ChangesAlertView({
                el: "#staging-modal-changes",
                node: [data]
            });
            App.instances.changes.render();
            App.instances.changes.$el.find(".modal").modal();
        } else {
            App.instances.changes.data.nodes.push(data);
            view = new ChangesAlertView({
                node: App.instances.changes.data
            });
            view.render();
            App.instances.changes.$el.find(".nodes-changed").html(view.$el.find(".nodes-changed").html());
        }
    };

    App.getDomainModel = function (id) {
        var model, path, domain;
        model = App.instances.tree.findNodeById(id);
        path = model.path || model.get("path");
        domain = path.split(',').length === 2 ? id : path.split(',')[2];
        domain = new App.OU.Models.OUModel({ id: domain });
        return domain;
    };

    App.browserLanguage = (window.navigator.language || navigator.browserLanguage).slice(0, 2);

}(App, Backbone, jQuery, _));
