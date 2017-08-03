/*jslint browser: true, nomen: true, unparam: true */
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

App.module("User.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.UserModel = App.Policies.Models.GecosResourceModel.extend({
        resourceType: "user",

        defaults: {
            type: "user",
            lock: false,
            source: "gecos",
            first_name: "",
            last_name: "",
            name: "",
            address: "",
            phone: "",
            email: "",
            commentaries: "",			
            policyCollection: new App.Policies.Models.PolicyCollection(),
            isEditable: undefined,
            computer_names: []
        }
    });
});

App.module("User.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.UserForm = App.GecosFormItemView.extend({
        template: "#user-template",
        tagName: "div",
        className: "col-sm-12",

        groupsWidget: undefined,

        ui: {
            policies: "div#policies div.bootstrap-admin-panel-content"
        },

        events: {
            "click #submit": "saveForm",
            "click #delete": "deleteModel",
            "click #cut": "cutModel",
            "change input": "validate",
            "click button.refresh": "refresh"
        },

        policiesList: undefined,

        onBeforeRender: function () {
            var path = this.model.get("path"),
                domain,
                that = this,
                isEditable;

            //CHECK IS EMPTY
            var computers = this.model.get("computers"),
                path = this.model.get("path"),
                id = this.model.get("id"),
                that = this;

            if(typeof App.instances.noMaintenance == 'undefined'){
                App.instances.noMaintenance = [];
            }

            var page = new App.Tree.Models.Container({path:path+','+id});
            page.goTo(1, {
               success: function (data) {
                   var $button = $('#delete');
                   if(!_.isEmpty(computers)) {
                        $button.removeClass('btn-danger');
                        $button.addClass('btn-group');
                        $button.removeAttr('id');
                        $button.unbind('click');
                        $button.css('margin-right','5px');
                        $button.click(function (e){
                           e.preventDefault();
                           App.showAlert('warning',
                                         gettext('Can not delete user because it is linked to a computer.'),
                                         "<br/> - " + gettext("Delete first locally on the computer"));

                        });
                        App.instances.noMaintenance[that.model.get('id')] = false;
                   }
                }
            });

            if (this.model.get("isEditable") !== undefined) { return; }
            domain = path.split(',')[2];

            if (path.split(',')[0] === "undefined") {
                this.model.set("isEditable", true);
            } else {
                domain = new App.OU.Models.OUModel({ id: domain });
                domain.fetch().done(function () {
                    isEditable = domain.get("master") === "gecos";
                    if (!isEditable) { isEditable = that.model.get("source") === "gecos"; }
                    that.model.set("isEditable", isEditable);
                    that.model.set("master_policies", isEditable ? [] : domain.get("master_policies"));
                    that.render();
                });
            }

        },

        onRender: function () {
            if (!_.isUndefined(this.model.id)) {
                this.$el.find("#username").attr('disabled', 'disabled');
            }

            this.groupsWidget = new App.Group.Views.MultiGroupWidget({
                el: this.$el.find("div#groups-widget")[0],
                item_id: this.model.get("id"),
                ou_id: _.last(this.model.get("path").split(',')),
                checked: this.model.get("memberof"),
                disabled: !this.model.get("isEditable"),
                name: this.model.get("name")
            });
            this.groupsWidget.render();

            this.policiesList = new App.Policies.Views.PoliciesList({
                el: this.ui.policies[0],
                collection: this.model.get("policyCollection"),
                resource: this.model
            });
            this.policiesList.render();
            if (!this.model.get("isEditable")) {
                this.$el.find("textarea,input,select").prop("disabled", true).prop("placeholder", '');
            }

        },

        saveForm: function (evt) {
            evt.preventDefault();
            this.saveModel($(evt.target), {
                memberof: _.bind(this.groupsWidget.getChecked, this.groupsWidget),
                name: "#username",
                phone: "#phone",
                email: "#email",
                first_name: "#firstname",
                last_name: "#lastname",
                address: "#address",
				commentaries: "#commentaries"				
            });
        }
    });
});
