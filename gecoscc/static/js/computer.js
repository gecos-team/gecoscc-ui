/*jslint browser: true, nomen: true, unparam: true, vars: false */
/*global App, gettext */

/*
* Copyright 2013, Junta de Andalucia
* http://www.juntadeandalucia.es/
*
* Authors:
*   Alberto Beiztegui <albertobeiz@gmail.com>
*   Alejandro Blanco <alejandro.b.e@gmail.com>
*   Emilio Sanchez <emilio.sanchez@gmail.com>
*
* All rights reserved - EUPL License V 1.1
* https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
*/

App.module("Computer.Models", function (Models, App, Backbone, Marionette, $, _) {
    "use strict";

    Models.ComputerModel = App.Policies.Models.GecosResourceModel.extend({
        resourceType: "computer",

        defaults: {
            type: "computer",
            lock: false,
            source: "gecos",
            name: "",
            registry: "",
            serial: "",
            family: "",
            users: [],
            uptime: "-",
            gcc_link: true,
            ipaddress: "",
            commentaries: "",
            product_name: "",
            manufacturer: "-",
            cpu: "",
            ohai: "",
            ram: "",
            lsb: {},
            kernel: {},
            filesystem: {},
            policyCollection: new App.Policies.Models.PolicyCollection(),
            isEditable: undefined,
            icon: "desktop",
            labelClass: "label-success",
            iconClass: "info-icon-success",
            error_last_saved: false,
            error_last_chef_client: true
        }
    });
});

App.module("Computer.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.ComputerForm = App.GecosFormItemView.extend({
        template: "#computer-template",
        tagName: "div",
        className: "col-sm-12",

        groupsWidget: undefined,
        policiesList: undefined,
        inheritanceList: undefined,
        activeTab: undefined,

        ui: {
            groups: "div#groups-widget",
            policies: "div#policies div.bootstrap-admin-panel-content",
            inheritance: "div#inheritance div.bootstrap-admin-panel-content"
        },

        events: {
            "click #submit": "saveForm",
            "click #delete": "deleteModel",
            "click #cut": "cutModel",
            "change input": "validate",
            "click button.refresh": "refresh",
            "click button.support": "support",
        },

        onBeforeRender: function () {
            this.checkErrors();

            //Set domain dependent atributes
            var path = this.model.get("path"),
                ram = this.model.get("ram");

            if (!_.isUndefined(this.model.get("isEditable"))) { return; }

            if (!_.isUndefined(path.split(',')[0])) {
                this.model.set("isEditable", true);
            } else {
                this.getDomainAttrs();
            }

            if (!_.isUndefined(ram)) {
                // remove units and convert to MB
                ram = ram.slice(0, -2);
                ram = parseInt(ram, 10) / 1024;
                ram = ram.toFixed() + " MB";
                this.model.set("ram", ram);
            }
        },

        checkErrors: function () {
            var now = new Date(),
                ohai = this.model.get("ohai"),
                lastConnection,
                interval,
                chef_client;

            this.model.set("iconClass", "info-icon-success");
            this.model.set("labelClass", "label-success");

            lastConnection = new Date(this.model.get("ohai").ohai_time * 1000);
            this.model.set("last_connection", this.calculateTimeToNow(lastConnection));


            if (ohai === "") {
                this.alertError(
                    gettext("No data has been received from this workstation."),
                    gettext("Check connection with Chef server.")
                );
                return;
            }

            if (_.isUndefined(ohai.ohai_time)) {
                this.model.set("last_connection", "Error");
                this.alertWarning(
                    gettext("This workstation is not linked."),
                    gettext("It is possible that this node was imported from AD or LDAP.")
                );
                return;
            }

            chef_client = ohai.chef_client;
            if (_.isUndefined(chef_client)) {
                this.alertError(gettext("This workstation has incomplete Ohai information."));
                return;
            }

            if (this.model.get("error_last_saved")) {
                this.model.set("iconClass", "info-icon-danger");
                App.showAlert(
                    "error",
                    gettext("This workstation is not working properly:"),
                    "<br/> - " + gettext("There were errors while saving this node in Chef")
                );
                return;
            }
 
            if (!this.model.get("gcc_link")) {
                this.alertWarning(
                    gettext("This workstation is not working properly:"),
                     "<br/> - " + gettext("Network problems connecting to the Control Center.")
                );
                return;
            }

            if (this.model.get("error_last_chef_client")) {
                this.model.set("iconClass", "info-icon-danger");
                App.showAlert(
                    "error",
                    gettext("This workstation is not working properly:"),
                    "<br/> - " + gettext("Last synchronization had problems during its execution.")
                );
                return;
            }

            interval = App.update_error_interval || 24;
            now.setHours(now.getHours() - interval);
            if (lastConnection < now) {
                this.alertWarning(
                    gettext("This workstation is not working properly:"),
                    "<br/> - " + gettext("Synchronization is not being executed on time.")
                );
            }
        },

        alertError: function (strong, text) {
            this.model.set("uptime", "-");
            this.model.set("last_connection", "Error");
            this.model.set("iconClass", "info-icon-danger");
            this.model.set("labelClass", "label-danger");
            App.showAlert(
                "error",
                strong,
                text
            );
        },

        alertWarning: function (strong, text) {
            this.model.set("uptime", "-");
            this.model.set("gcc_link", false);
            this.model.set("iconClass", "info-icon-warning");
            this.model.set("labelClass", "label-warning");
            App.showAlert(
                "warning",
                strong,
                text
            );
        },

        calculateTimeToNow: function (time) {
            var date_future = time,
                date_now = new Date(),
                seconds = Math.floor((date_now - date_future) / 1000),
                minutes = Math.floor(seconds / 60),
                hours = Math.floor(minutes / 60),
                days = Math.floor(hours / 24);

            hours = hours - (days * 24);
            minutes = minutes - (days * 24 * 60) - (hours * 60);
            seconds = seconds - (days * 24 * 60 * 60) - (hours * 60 * 60) - (minutes * 60);

            return [days, gettext("Days"), hours, gettext("Hours"), minutes, gettext("Minutes")].join(" ");
        },


        ohaiTreeDataSource: function(parentData, callback) {
            var ohai = this.model.get("ohai");
            var path = '/';
            var id_base = '';

            if (typeof(parentData.content) !== 'undefined') {
                ohai = parentData.content;
                path = parentData.path + parentData.key.replace(/[^a-zA-Z0-9]/g, '_') + '/';
                id_base = parentData.id_base + "_" + parentData.key.replace(/[^a-zA-Z0-9]/g, '_');
            }
            
            var childNodesArray = [];
            for( var name in ohai ) {
                var id = id_base + "_" + name.replace(/[^a-zA-Z0-9]/g, '_');
                if (Array.isArray(ohai[name]) || (typeof(ohai[name])) === 'object') {
                    // Folder
                    var cssClass = "tree-json-object";
                    if (Array.isArray(ohai[name])) {
                        cssClass = "tree-json-array";
                    }
                    if (ohai[name] === null) {
                        cssClass = "tree-json-null";
                        childNodesArray.push( {"id_base": id_base, "key": name, "path": path, "name": name+': <span class="tree-json-null">null</span>', "type": "item", content: ohai[name], "attr": { "id": id, "data-icon": "icon-tree-json-null" }  } );
                    }
                    else {
                        childNodesArray.push( {"id_base": id_base, "key": name, "path": path, "name": name+":", "type": "folder", content: ohai[name], "attr": { "id": id, "hasChildren": !($.isEmptyObject(ohai[name])), "cssClass": cssClass }  } );
                    }
                }
                else {
                    // Item
                    var name_value = name+': <span class="tree-json-'+(typeof(ohai[name]))+'">'+ohai[name]+'</span>';
                    if (typeof(ohai[name]) === 'string') 
                        name_value = name+': <span class="tree-json-'+(typeof(ohai[name]))+'">"'+ohai[name]+'"</span>';
                    
                    if (Array.isArray(ohai)) {
                        name_value = '<span class="tree-json-'+(typeof(ohai[name]))+'">'+ohai[name]+'</span>';
                        if (typeof(ohai[name]) === 'string') {
                            name_value = '<span class="tree-json-'+(typeof(ohai[name]))+'">"'+ohai[name]+'"</span>';
                        }
                        
                    }
                    
                    if (ohai === null)
                        name_value = '<span class="tree-json-null">null</span>';
                
                    childNodesArray.push( {"key": name, "path": path, "name": name_value, "type": "item", "attr": { "id": id, "data-icon": "icon-tree-json-"+(typeof(ohai[name])) } } );
                }
            }
            
            
            callback({
              data: childNodesArray
            });
        },
        
        ohaiTreeDiscloseSaved: function(ohai_tree) {
            var openNodes = {};
            if(jQuery.type(Cookies.get('json_tree_opened_nodes')) != "undefined") {
                openNodes = JSON.parse(Cookies.get('json_tree_opened_nodes'));
            }
            if (jQuery.type(openNodes[username]) == "undefined") {
                openNodes[username] = []
            }
            if (jQuery.type(openNodes['current']) == "undefined") {
                openNodes['current'] = this.model.get("id");
            }
           
            
            for (var i=0; i < openNodes[username].length; i++) {
                var node_id = openNodes[username][i];
                
                ohai_tree.tree('openFolder', ohai_tree.find('#'+node_id));
            }
        },
        
        ohaiTreeDiscloseAll: function(ohai_tree) {
            // This is slow!
            //ohai_tree.tree('discloseAll');

            var isAllDisclosed = ohai_tree.find( ".tree-branch:not('.tree-open, .hidden, .hide')" ).length === 0;
            if (!isAllDisclosed) {
                // Expanding the tree when its not visible is faster (because the browser doesn't need to draw the changes until the end), 
                // so we will create a new one expand it and after that replace the current visible tree
                var tree_parent = ohai_tree.parent();
                var ohai_tree_original = ohai_tree;

                // Create a new empty tree
                ohai_tree = ohai_tree.clone();
                ohai_tree.find( "li:not([data-template])" ).remove();
                
                // Render the new tree
                ohai_tree.tree({ dataSource: this.ohaiTreeDataSource, model: this.model }); 

//                var start, end;
//                start = Date.now();
                
                // Open all the branches
                while (!isAllDisclosed) {
                    ohai_tree.tree('discloseVisible');
                    isAllDisclosed = ohai_tree.find( ".tree-branch:not('.tree-open, .hidden, .hide')" ).length === 0;
                }
                
//                end = Date.now();
//                console.log("discloseVisible: "+(end-start)+"ms");
                
                // Replace the tree
                var that = this;
                ohai_tree.on('disclosedFolder.fu.tree closed.fu.tree',                
                    function(event, parentData) {
                        that.saveTreeStatus(event, parentData, that);
                    }
                );
                this.clearSavedState();
                
                tree_parent.find('#ohai_tree').remove();
                tree_parent.append(ohai_tree);
            }
                
        },        
        
        ohaiTreeCloseAll: function(ohai_tree) {
            // This is slow!
            //ohai_tree.tree('closeAll');

            // Remove the tree data and render it again
            ohai_tree.find( "li:not([data-template])" ).remove();
            ohai_tree.tree('render');
            this.clearSavedState();
        },
        
        ohaiTreeDataSearch: function(ohai_tree, keyword, mode) {
            var ohai = this.model.get("ohai");

            // Get current selected item
            var selectedItemPath = '/';
            if (mode != 'initial') {
                if (ohai_tree.tree('selectedItems').length > 0) {
                    var selectedItem = ohai_tree.tree('selectedItems')[0];
                    selectedItemPath = selectedItem.path + selectedItem.key.replace(/[^a-zA-Z0-9]/g, '_');
                }
            }

            
            // Look for the next result
            var result = this.ohaiTreeDataSearchNextResult(ohai_tree, keyword, ohai, selectedItemPath, '', false, mode);
            var nextResultPath = result[0];
            // console.log('nextResultPath: '+nextResultPath);
            
            if (nextResultPath) {
                // Result found
                this.$el.find("#ohai_tree-search").css('background-color', 'white');
                
                // Close the tree
                this.ohaiTreeCloseAll(ohai_tree);
                
                // Open the result
                var parts = nextResultPath.substring(1).split("/");
                for (var i = 1; i<=parts.length; i++) {
                    var folderId = '#';
                    for (var j = 0; j<i; j++) {
                        folderId += '_'+parts[j].replace(/[^a-zA-Z0-9]/g, '_');
                    }
                    
                    if (i<parts.length) {
                        // Open container folder
                        ohai_tree.tree('openFolder', $(folderId));
                    }
                    else {
                        // Select result
                        var attr = $(folderId).attr('haschildren');
                        if (typeof attr !== typeof undefined) {
                            ohai_tree.tree('selectFolder', $(folderId));
                        }
                        else {
                            ohai_tree.tree('selectItem', $(folderId));
                        }
                        
                        if ($(folderId).length <= 0) {
                            alert('Can\'t find:' + folderId);
                        }
                        var top = $(folderId).position().top;
                        //console.log('top: '+top+' scrolltop:'+ohai_tree.scrollTop());
                        
                        ohai_tree.scrollTop( ohai_tree.scrollTop() + $(folderId).position().top);
                        
                    }
                }
                
                
                
                
            }
            else {
                // No result
                this.$el.find("#ohai_tree-search").css('background-color', 'red');
            }
            
            
        },
        
        ohaiTreeDataSearchNextResult: function(ohai_tree, keyword, data, selectedItemPath, path, passed, mode) {
            if (data === null) {
                return [false, passed];
            }
            
            if (selectedItemPath == '/') {
                passed = true;
            }
            
            if (mode == 'previous') {
                var lastValue = [false, passed];
                var current = this.ohaiTreeDataSearchNextResult(ohai_tree, keyword, data, '/', '', false, 'initial');
                // console.log('current: '+current[0]+' selectedItemPath:'+selectedItemPath);
                while (current[0] != selectedItemPath) {
                    // console.log('current: '+current[0]+' selectedItemPath:'+selectedItemPath);
                    lastValue = current;
                    current = this.ohaiTreeDataSearchNextResult(ohai_tree, keyword, data, lastValue[0], '', false, 'next');
                }
                
                return lastValue;
            }
            
            var keys = Object.keys(data);
            for( var i=0; i<keys.length; i++ ) {
                var name = keys[i];
                var currentPath = path + '/' + name.replace(/[^a-zA-Z0-9]/g, '_');
                var value = data[name];
                //console.log('currentPath: '+currentPath+' passed = '+passed);
                
                if (currentPath == selectedItemPath) {
                    passed = true;
                    if (!Array.isArray(value) && typeof(value) !== 'object') {
                        continue;
                    }
                }
                else if (name.match(keyword) && passed) {
                    // Next result found in key
                    return [currentPath, passed];
                }
                 
                if (Array.isArray(value) || typeof(value) === 'object') {
                   var res = this.ohaiTreeDataSearchNextResult(ohai_tree, keyword, value, selectedItemPath, currentPath, passed, mode);
                   if (res[0]) {
                       return res;
                   }
                   else {
                       passed = res[1];
                   }
                }
                else if (typeof(value) === 'string' && value.match(keyword) && passed) {
                    // Next result found in value
                    return  [currentPath, passed];
                }
                else if (typeof(value) !== 'string' && (value+'').match(keyword) && passed) {
                    // Next result found in value
                    return  [currentPath, passed];
                }
               
            }
            
            return [false, passed];
            
        },        

        checkCurrentComputer: function(computer_id) {
            var openNodes = {};
            if(jQuery.type(Cookies.get('json_tree_opened_nodes')) != "undefined") {
                openNodes = JSON.parse(Cookies.get('json_tree_opened_nodes'));
            }
            if (jQuery.type(openNodes[username]) == "undefined") {
                openNodes[username] = []
            }
            if (jQuery.type(openNodes['current']) == "undefined") {
                openNodes['current'] = 0;
            }

            return (openNodes['current'] == this.model.get("id"))
        },
        
        /**
         * Adds a node to the list of open nodes.
         * @node_id Node ID to add to the list.
         */
        saveOpenNode: function(node_id) {
            if (this.isNodeOpen(node_id)) {
                // Already opened
                return;
            }
            
            var openNodes = {};
            if(jQuery.type(Cookies.get('json_tree_opened_nodes')) != "undefined") {
                openNodes = JSON.parse(Cookies.get('json_tree_opened_nodes'));
            }
            if (jQuery.type(openNodes[username]) == "undefined") {
                openNodes[username] = []
            }
            if (jQuery.type(openNodes['current']) == "undefined") {
                openNodes['current'] = this.model.get("id");
            }
            
            
            openNodes[username].push(node_id); 
            Cookies.set('json_tree_opened_nodes',  JSON.stringify(openNodes));
            
        },
        
        /**
         * Removes a node to the list of open nodes.
         * @node_id Node ID to remove from the list.
         */
        saveCloseNode: function(node_id) {
            var openNodes = {};
            if(jQuery.type(Cookies.get('json_tree_opened_nodes')) != "undefined") {
                openNodes = JSON.parse(Cookies.get('json_tree_opened_nodes'));
            }
            if (jQuery.type(openNodes[username]) == "undefined") {
                openNodes[username] = []
            }
            if (jQuery.type(openNodes['current']) == "undefined") {
                openNodes['current'] = this.model.get("id");
            }
            
            
            if (openNodes[username].indexOf(node_id) < 0) {
                return;
            }
            
            openNodes[username].splice(openNodes[username].indexOf(node_id), 1);
            Cookies.set('json_tree_opened_nodes',  JSON.stringify(openNodes));
        },
                
                
        /**
         * Checks if a node is in the list of open nodes.
         * @node_id Node ID to check.
         * @returns true if the node is in the list.
         */
        isNodeOpen: function(node_id) {
            var openNodes = {};
            if(jQuery.type(Cookies.get('json_tree_opened_nodes')) != "undefined") {
                openNodes = JSON.parse(Cookies.get('json_tree_opened_nodes'));
            }            
            if (jQuery.type(openNodes[username]) == "undefined") {
                openNodes[username] = []
            }
            if (jQuery.type(openNodes['current']) == "undefined") {
                openNodes['current'] = this.model.get("id");
            }
            
            
            return (openNodes[username].indexOf(node_id) >= 0);
        },
          
        /**
         * Clears the state saved in cookies.
         */
        clearSavedState: function() {
            Cookies.remove('json_tree_opened_nodes');
        },
          
          
        /**
         * Open and close node handler.
         */
        saveTreeStatus: function(event, parentData, that) {
            var id_base = parentData.id_base + "_" + parentData.key.replace(/[^a-zA-Z0-9]/g, '_');
            if (event.type == "disclosedFolder") {
                // opened
                that.saveOpenNode(id_base);
            }
            else {
                // closed
                that.saveCloseNode(id_base);
            }
        },

        onShow: function () {
            if (!_.isNull(App.instances.activeTab)) {
                $('a[href="#' + App.instances.activeTab  + '"]').tab('show');
            }
        },
        
        onRender: function () {

            this.check_permissions();

            if(!_.isUndefined(this.activeTab)) {
                this.activeTab = this.activeTab;
                this.$el.find('#' + this.activeTab.id + ' a[href="' + this.activeTab.firstElementChild.getAttribute('href') + '"]').tab('show');
            }
            this.$el.find('[data-toggle="tooltip"]').tooltip();

            if (!_.isUndefined(this.model.id)) {
                this.$el.find("#name").attr('disabled', 'disabled');
            }

            this.groupsWidget = new App.Group.Views.MultiGroupWidget({
                el: this.ui.groups[0],
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

            this.inheritanceList = new App.Inheritance.Views.InheritanceList({
                el: this.ui.inheritance[0],
                resource: this.model
            });
            this.inheritanceList.render();

            this.$el.find("#ohai-json").click(function (evt) {
                var $el = $(evt.target).find("span.fa");
                $el.toggleClass("fa-caret-right").toggleClass("fa-caret-down");
            });
            if (!this.model.get("isEditable")) {
                // Disable edit textarea, input and select except the
                // search button
                this.$el.find("textarea,input,select").prop("disabled", true).prop("placeholder", '');
                this.$el.find("#ohai_tree-search").
                    prop("placeholder", 'Buscar').removeProp("disabled");
                    
                // Disable delete log button
                var $rmLog = this.$el.find(".deleteLogBtn");
                $rmLog.addClass('disabled');
                $rmLog.unbind('click');                
            }
            
            // OHAI JSON tree rendering
            var that = this;
            var ohai_tree = this.$el.find("#ohai_tree");
            ohai_tree.tree({ dataSource: this.ohaiTreeDataSource, model: this.model });
            
            if (this.checkCurrentComputer(this.model.get("id"))) {
                // Reloading the same computer
                this.ohaiTreeDiscloseSaved(ohai_tree);
                this.$el.find("#ohai-json").click();
            }
            else {
                // The user has selected a new computer
                this.clearSavedState();
            }
            
            ohai_tree.on('disclosedFolder.fu.tree closed.fu.tree', 
               function(event, parentData) {
                    that.saveTreeStatus(event, parentData, that);
               }
            );
            
            // OHAI JSON tree buttons
            this.$el.find("#ohai_tree-expand")
                .off("click")
                .on("click", function (evt) {
                    evt.preventDefault();
                    $(this).find(".normal").hide();
                    $(this).find(".loading").show();
                    
                    var thisbutton = $(this);
                    setTimeout(function(){ 
                        var ohai_tree = that.$el.find("#ohai_tree");
                        that.ohaiTreeDiscloseAll(ohai_tree);
                        thisbutton.find(".loading").hide();
                        thisbutton.find(".normal").show();
                    }, 10);

                });            

            this.$el.find("#ohai_tree-compress")
                .off("click")
                .on("click", function (evt) {
                    evt.preventDefault();
                    
                    $(this).find(".normal").hide();
                    $(this).find(".loading").show();
                    
                    var thisbutton = $(this);
                    setTimeout(function(){ 
                        var ohai_tree = that.$el.find("#ohai_tree");
                        that.ohaiTreeCloseAll(ohai_tree);
                        thisbutton.find(".loading").hide();
                        thisbutton.find(".normal").show();
                    }, 10);
                    
                    
                });            

                
            var search_field = this.$el.find("#ohai_tree-search");
            this.$el.find("#ohai_tree-close-search-btn")
                .off("click")
                .on("click", function (evt) {
                    evt.preventDefault();
                    search_field.val('');
                    search_field.css('background-color', 'white');
                    $("#ohai_tree-close-search-btn").hide();
                    $("#ohai_tree-next-search-btn").hide();
                    $("#ohai_tree-previous-search-btn").hide();                    
                });
            
            
            this.$el.find("#ohai_tree-search-btn")
                .off("click")
                .on("click", function (evt) {
                    evt.preventDefault();
                    var keyword = search_field.val().trim();
                    if (!keyword) {
                        // Disable search
                        $("#ohai_tree-close-search-btn").hide();
                        $("#ohai_tree-next-search-btn").hide();
                        $("#ohai_tree-previous-search-btn").hide();
                    }
                    else {
                        // Start search
                        var keyword = new RegExp(keyword.replace(/\./g, '\\.'), "i");
                        var ohai_tree = that.$el.find("#ohai_tree");
                        that.ohaiTreeDataSearch(ohai_tree, keyword, 'initial');


                        $("#ohai_tree-close-search-btn").show();
                        $("#ohai_tree-next-search-btn").show();
                        $("#ohai_tree-previous-search-btn").show();

                    }
                    
                }); 

            //click button when enter key is pressed
            search_field.keyup(function (evt) {
                search_field.css('background-color', 'white');
                if (evt.which === 13) {
                    $("#ohai_tree-search-btn").click();
                }
            });                
                
            this.$el.find("#ohai_tree-next-search-btn")
                .off("click")
                .on("click", function (evt) {
                    evt.preventDefault();
                    var keyword = search_field.val().trim();
                    if (keyword) {
                        // Next search result
                        var keyword = new RegExp(keyword.replace(/\./g, '\\.'), "i");
                        var ohai_tree = that.$el.find("#ohai_tree");
                        that.ohaiTreeDataSearch(ohai_tree, keyword, 'next');
                    }
                    
                });                 

            this.$el.find("#ohai_tree-previous-search-btn")
                .off("click")
                .on("click", function (evt) {
                    evt.preventDefault();
                    var keyword = search_field.val().trim();
                    if (keyword) {
                        // Next search result
                        var keyword = new RegExp(keyword.replace(/\./g, '\\.'), "i");
                        var ohai_tree = that.$el.find("#ohai_tree");
                        that.ohaiTreeDataSearch(ohai_tree, keyword, 'previous');
                    }
                    
                });                 

                
            // Ensure the execution of onShow after onRender
            this.onShow();                
        },
        
        refresh: function (evt) {

            this.activeTab = this.$el.find('.nav-tabs li.active')[0];

            var that = this;
            if (!_.isUndefined(evt)) {
                evt.preventDefault();
            }
            App.instances.staging.dropModel(this.model);
            $("#alerts-area .alert").slideUp('fast', function () {
                $(this).find("button.close").click();
            });
            $(this.el).fadeOut(function () {
                that.model.fetch().done(function () {
                    that.render();
                }).done(function () {
                    $(that.el).fadeIn();
                });
            });
        },
        
        
        support: function (evt) {
            // Open support Window for this computer 
            window.open('/api/computers/support/'+this.model.get('id')+'/', 'support');
        },        

        saveForm: function (evt) {
            evt.preventDefault();
            this.saveModel($(evt.target), {
                memberof: _.bind(this.groupsWidget.getChecked, this.groupsWidget),
                name: "#name",
                family: "#family option:selected",
                registry: "#registry",
                serial: "#serial",
                commentaries: "#commentaries"
            });
        }
    });
});
