/*jslint browser: true, nomen: true, vars: false */
/*global App: true, Backbone, jQuery, _, gettext */

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

// This file creates the global App variable, it should be loaded as soon as
// possible
var App;

(function (Backbone, $, _, gettext) {
    "use strict";

    var Router,
        HomeView,
        NewElementView,
        LoaderView,
        numericRegex,
        emailRegex,
        ipRegex,
        urlRegex,
        applyRegex;

    App = new Backbone.Marionette.Application();

    // To store references to root instances
    App.instances = {};

    App.addRegions({
        // sidebar
        tree: "#ex-tree",
        events: "#events",
        // breadcrumb
        breadcrumb: "#breadcrumb",
        // main
        main: "#viewport-main"
    });

    Router = Backbone.Marionette.AppRouter.extend({
        appRoutes: {
            "": "loadHome",
            "ou/:containerid/new": "newItemDashboard",
            "ou/:containerid/user": "newUser",
            "ou/:containerid/user/:userid": "loadUser",
            "ou/:containerid/ou": "newOU",
            "ou/:containerid/ou/:ouid": "loadOU"
        },

        controller: {
            loadHome: function () {
                var view = new HomeView();
                App.instances.breadcrumb.setSteps([]);
                App.tree.$el
                    .find(".tree-selected")
                    .removeClass("tree-selected");
                App.main.show(view);
            },

            newItemDashboard: function (containerid) {
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/new",
                    text: gettext("New element")
                }]);

                App.instances.newElementView.containerId = containerid;
                App.main.show(App.instances.newElementView);
            },

            _newItemHelper: function (Model, View, containerid) {
                var model = new Model({}),
                    view = new View({ model: model }),
                    parent,
                    path;

                // Render the loader indicator
                App.main.show(App.instances.loaderView);
                parent = App.instances.tree.get("tree").first(function (n) {
                    return n.model.id === containerid;
                });
                path = parent.model.path + ',' + parent.model.id;
                model.set("path", path);

                App.main.show(view);
            },

            newUser: function (containerid) {
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/user",
                    text: gettext("User")
                }]);
                this._newItemHelper(
                    App.User.Models.UserModel,
                    App.User.Views.UserForm,
                    containerid
                );
            },

            newOU: function (containerid) {
                App.instances.breadcrumb.setSteps([{
                    url: "ou/",
                    text: gettext("Organisational Unit")
                }]);
                this._newItemHelper(
                    App.OU.Models.OUModel,
                    App.OU.Views.OUForm,
                    containerid
                );
            },

            _loadItemHelper: function (Model, View, id) {
                var model, view, skipFetch;

                model = App.instances.cache.get(id);
                if (_.isUndefined(model)) {
                    model = new Model({ id: id });
                    App.instances.cache.set(id, model);
                } else {
                    skipFetch = true;
                }
                view = new View({ model: model });

                // Render the loader indicator
                App.main.show(App.instances.loaderView);
                model
                    .off("change")
                    .on("change", function () {
                        App.main.show(view);
                    });

                if (skipFetch) {
                    model.trigger("change");
                } else {
                    model.fetch().done(function () {
                        // Item loaded, now we need to update the tree
                        var node = App.instances.tree.get("tree").first(function (n) {
                                return n.model.id === id;
                            }),
                            promise = $.Deferred();

                        if (node && node.model.loaded) {
                            promise.resolve();
                        } else {
                            promise = App.instances.tree.loadFromNode(
                                model.get("path"),
                                model.get("id"),
                                true
                            );
                        }
                        promise.done(function () {
                            App.tree.currentView.selectItemById(id);
                        });
                    });
                }
            },

            loadUser: function (containerid, userid) {
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/user/" + userid,
                    text: gettext("User")
                }]);
                this._loadItemHelper(
                    App.User.Models.UserModel,
                    App.User.Views.UserForm,
                    userid
                );
            },

            loadOU: function (containerid, ouid) {
                App.instances.breadcrumb.setSteps([{
                    url: "ou/" + containerid + "/ou" + ouid,
                    text: gettext("Organisational Unit")
                }]);
                this._loadItemHelper(
                    App.OU.Models.OUModel,
                    App.OU.Views.OUForm,
                    ouid
                );
            }
        }
    });

    App.instances.router = new Router();

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

    App.GecosFormItemView = Backbone.Marionette.ItemView.extend({
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
                }
            });

            return valid;
        }
    });

    HomeView = Backbone.Marionette.ItemView.extend({
        template: "#home-template",

        onRender: function () {
            this.$el.find('.easyPieChart').easyPieChart({
                animate: 1000
            });
        }
    });

    NewElementView = Backbone.Marionette.ItemView.extend({
        template: "#new-element-template",

        serializeData: function () {
            // This view needs no model
            return {
                ouID: this.containerId
            };
        }
    });

    App.instances.newElementView = new NewElementView();

    LoaderView = Backbone.Marionette.ItemView.extend({
        template: "#loader-template",

        serializeData: function () {
            return {}; // This view needs no model
        }
    });

    App.instances.loaderView = new LoaderView();

    App.on('initialize:after', function () {
        var path = window.location.hash.substring(1);

        if (Backbone.history) {
            Backbone.history.start();
        }

        App.instances.router.navigate(path, { trigger: true });
    });
}(Backbone, jQuery, _, gettext));
