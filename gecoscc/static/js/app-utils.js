/*jslint browser: true, vars: false, nomen: true */
/*global App, Backbone, jQuery, _, gettext, interpolate */

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

(function (App, Backbone, $, _) {
    "use strict";

    var AlertView, numericRegex, emailRegex, ipRegex, urlRegex, applyRegex, urlExtendRegex;

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

        save: function () {
            return App.instances.staging.add(this, { arguments: arguments });
        },

        destroy: function () {
            return App.instances.staging.add(this, {
                arguments: arguments,
                destroy: true
            });
        }
    });

    App.GecosFormItemView = Backbone.Marionette.ItemView.extend({
        // a resourceType property should be declared by models that use
        // this view for edition, example:
        //
        // resourceType: "user",

        initialize: function () {
            this.listenTo(App, 'action_change', this.onActionChange);
            this.listenTo(App, 'action_delete', this.onActionDelete);
        },

        onRender: function () {
            if (!_.isUndefined(this.model.id)) {
                this.$el.find("#name").attr('disabled', 'disabled');
            }
        },

        onActionChange: function (obj) {
            if (this.model.id === obj._id) {
                App.showAlert(
                    "error",
                    gettext("Object changed."),
                    gettext("Someone has changed this object while you were working on it, please reload before applying any changes.")
                );
                this.disableSave();
            }
        },

        onActionDelete: function (obj) {
            if (this.model.id === obj._id) {
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
            $(this.el).fadeOut(function () {
                that.groupsWidget = undefined;
                that.policiesList = undefined;
                that.model.fetch().done(function () {
                    that.render();
                }).done(function () {
                    $(that.el).fadeIn(function () {
                        $("#alerts-area .alert").slideUp(function () {
                            $(this).find("button.close").click();
                        });
                    });
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

        _errorMessage: function (id, response) {
            var message = [
                gettext("Something went wrong, please try again in a few moments."),
                interpolate(gettext("Resource ID: %s"), [id])
            ];

            if (_.has(response, "status") && _.has(response, "statusText")) {
                message.push("- " + gettext("Status") + response.status +
                             ": " + response.statusText);
            }
            return message.join(' ');
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

            this._showSavingProcess($button, "progress");
            _.each(_.pairs(mapping), function (relation) {
                that._setPropInModel(relation[0], relation[1]);
            });

            promise = this.model.save();
            setTimeout(function () {
                that._showSavingProcess($button, "saved");
            }, 1000);

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
                if (response !== "avoid alert") {
                    App.showAlert(
                        "error",
                        interpolate(gettext("Saving the %s failed."), [that.model.resourceType]),
                        that._errorMessage(that.model.get("id"), response)
                    );
                }
            });

            return promise;
        },

        deleteModel: function (evt) {
            evt.preventDefault();
            var that = this,
                $button = $(evt.target),
                promise;

            this._showSavingProcess($button, "progress");
            promise = this.model.destroy();
            setTimeout(function () {
                that._showSavingProcess($button, "success");
                App.instances.tree.trigger("change");
            }, 1000);

            promise.done(function () {
                // FIXME should it try to make it show the page where this node
                // (the one being deleted) was?
                App.instances.tree.loadFromPath(that.model.get("path"));
            });
            promise.fail(function (response) {
                if (response !== "avoid alert") {
                    App.showAlert(
                        "error",
                        interpolate(gettext("Couldn't delete the %s."), [that.model.resourceType]),
                        that._errorMessage(that.model.get("id"), response)
                    );
                }
            });
        },

        cutModel: function (evt) {
            evt.preventDefault();
            var that = this,
                $button = $(evt.target);

            this._showSavingProcess($button, "progress");
            App.instances.cut = this.model;
            setTimeout(function () {
                that._showSavingProcess($button, "success");
            }, 1000);
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
            }, 1000);
        }
    });

    App.showAlert = function (type, bold, text) {
        var view;

        if (type === "error") { type = "danger"; }
        view = new AlertView({
            type: type,
            bold: bold,
            text: text
        });
        App.alerts.show(view);
    };
}(App, Backbone, jQuery, _));
