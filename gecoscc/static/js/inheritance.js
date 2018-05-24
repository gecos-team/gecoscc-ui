/*jslint browser: true, vars: false, nomen: true, unparam: true */
/*global App, gettext */

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

App.module("Inheritance.Views", function (Views, App, Backbone, Marionette, $, _) {
    "use strict";

    Views.InheritanceList = Marionette.ItemView.extend({
        template: "#inheritance-list-template",
        tagName: "div",
        className: "col-sm-12",

        resource: null,

        initialize: function (options) {
            if (_.has(options, "resource")) {
                this.resource = options.resource;
            }
            this.collection = this.resource.get('inheritance');
        },
        
        serializeData: function () {
            return {items: this.collection,
                    resource: this.resource};
        },
        
        onRender: function () {
            // Inheritance JSON tree rendering
            var that = this;
            var inheritance_tree = this.$el.find("#inheritance_tree");
            inheritance_tree.tree({ dataSource: this.inheritanceTreeDataSource, model: this.resource.get('inheritance'), folderSelect:true });
            
            var isAllDisclosed = false;
            // Open all the branches
            while (!isAllDisclosed) {
                inheritance_tree.tree('discloseVisible');
                isAllDisclosed = inheritance_tree.find( ".tree-branch:not('.tree-open, .hidden, .hide')" ).length === 0;
            }
            
            // Replace icons
            inheritance_tree.find( "li.group-icon" ).find( "span.no-visited" ).removeClass('no-visited').removeClass('glyphicon-folder-open').addClass('fa fa-group');
            inheritance_tree.find( "li.user-icon" ).find( "span.no-visited" ).removeClass('no-visited').removeClass('glyphicon-folder-open').addClass('fa fa-user');
            inheritance_tree.find( "li.desktop-icon" ).find( "span.no-visited" ).removeClass('no-visited').removeClass('glyphicon-folder-open').addClass('fa fa-desktop');
            inheritance_tree.find( "li.folder-icon" ).find( "span.no-visited" ).removeClass('no-visited').removeClass('glyphicon-folder-open').addClass('fa fa-folder');
            inheritance_tree.find( "li.globe-icon" ).find( "span.no-visited" ).removeClass('no-visited').removeClass('glyphicon-folder-open').addClass('fa fa-globe');
            inheritance_tree.find( "li.flag-icon" ).find( "span.no-visited" ).removeClass('no-visited').removeClass('glyphicon-folder-open').addClass('fa fa-flag');
            
            // Disable unused buttons
            inheritance_tree.find( "li.user-icon" ).find( ".tree-branch-header" ).first().children().first().prop("disabled",true);
            inheritance_tree.find( "li.user-icon" ).find( ".tree-branch-header" ).first().children().first().css( "cursor", "default");
            inheritance_tree.find( "li.user-icon" ).find( ".tree-branch-header" ).first().children().first().css( "color", "black");
            inheritance_tree.find( "li.desktop-icon" ).find( ".tree-branch-header" ).first().children().first().prop("disabled",true);
            inheritance_tree.find( "li.desktop-icon" ).find( ".tree-branch-header" ).first().children().first().css( "cursor", "default");
            inheritance_tree.find( "li.desktop-icon" ).find( ".tree-branch-header" ).first().children().first().css( "color", "black");
            
            
            // Set selection manager
            inheritance_tree.on('selected.fu.tree', function(evt) {
                var selectedItem = inheritance_tree.tree('selectedItems');
                if (Array.isArray(selectedItem)) {
                    selectedItem = selectedItem[0];
                }
                if (('key' in selectedItem) && ('path' in selectedItem)  && ('attr' in selectedItem) && ('cssClass' in selectedItem.attr)) {
                    var obj_id = selectedItem.key.substring(1);
                    var path = selectedItem.path.split(',');
                    var parent_id = path[path.length-1];
                    var obj_type = 'unknown';
                    
                    switch(selectedItem.attr.cssClass) {
                        case 'group-icon':
                            obj_type = 'group';
                            break;
                        case 'user-icon':
                            obj_type = 'user';
                            break;
                        case 'desktop-icon':
                            obj_type = 'computer';
                            break;
                        case 'globe-icon':
                        case 'folder-icon':
                        case 'flag-icon':
                            obj_type = 'ou';
                            break;
                                
                    }
                    
                    //console.log("url: "+'/#ou/'+parent_id+'/'+obj_type+'/'+obj_id+'/policies');
                    if (obj_type=='ou' || obj_type == 'group') {
                        window.location = '/#ou/'+parent_id+'/'+obj_type+'/'+obj_id+'/policies';
                    }
                }
                inheritance_tree.tree('deselectAll');
                inheritance_tree.find(':focus').trigger( "blur" );
            });
        },        
        
        
        
        inheritanceTreeDataSource: function(parentData, callback) {
            var inheritance = this.model;
            
            if (!inheritance) {
                return;
            }
            
            var path = '/';
            var id_base = '';

            var childNodesArray = [];
            if (typeof(parentData) !== 'undefined' && ((typeof(parentData.children) !== 'undefined') || (typeof(parentData.policies) !== 'undefined')) ) {
                // Render policies
                if (typeof(parentData.policies) !== 'undefined') {
                    var policies = parentData.policies;
                    
                    for (var polciy_id in policies) {
                        var policy  = policies[polciy_id];
                        // Prepare icon type
                        var icon = 'fa-long-arrow-right';
                        if (policy["is_mergeable"]) {
                            icon = 'fa-random';
                        } 
                        
                        var name = policy['name'];
                        if (('name_'+App.language) in policy) {
                            name = policy['name_'+App.language];
                        }
                        if (!policy['inherited']) {
                            name = '<span class="no-inherited">'+name+'</span>';
                        }
                        
                        childNodesArray.push( {"key": 'h'+policy['_id'], "name": name, "type": "item", "attr": { "id": 'h'+policy['_id'], "data-icon": 'fa '+icon  } } )
                        
                    }                        
                }
                
                // Render nodes
                if (typeof(parentData.children) !== 'undefined') {
                    var children = parentData.children;
                    
                    for (var i=0; i < children.length; i++) {
                        var node  = children[i];
                        // Prepare icon type
                        var icon = 'folder-icon';
                        if (node["path"].split(",").length == 2) {
                            icon = 'globe-icon';
                        } 
                        if (node['type'] == 'computer') {
                            icon = 'desktop-icon';
                        }
                        else if (node['type'] == 'group') {
                            icon = 'group-icon';
                        }
                        else if (node['type'] == 'user') {
                            icon = 'user-icon';
                        }
                        
                        var name = node['name'];
                        if (node['is_main_element']) {
                            name = '<span class="inheritance_main_element">'+name+'</span>';
                        }
                        
                        childNodesArray.push( {"key": 'h'+node['_id'], "path": node['path'], 'is_main_element': node['is_main_element'], "name": name, "type": "folder", policies: node['policies'], children: node['children'], "attr": { "id": 'h'+node['_id'], "cssClass": icon } } )
                        
                        
                        
                    }
                }
                
            }
            else {
                var node = this.model;
                var icon = 'folder-icon';
                
                if (!node || !("path" in node) || node["path"]=='') {
                    // Empty inheritance data
                    return;
                }
                
                if (node["path"] == "root") {
                    icon = 'flag-icon';
                }
                else if (node["path"].split(",").length == 2) {
                    icon = 'globe-icon';
                } 
                if (node['type'] == 'group') {
                    icon = 'group-icon';
                }
                
                var name = node['name'];
                if (node['is_main_element']) {
                    name = '<span class="inheritance_main_element">'+name+'</span>';
                }                
                
                childNodesArray.push( {"key": 'h'+node['_id'], "path": node['path'], 'is_main_element': node['is_main_element'], "name": name, "type": "folder", policies: node['policies'], children: node['children'], "attr": { "id": 'h'+node['_id'], "cssClass": icon } } )
                
            }
            
            callback({
              data: childNodesArray
            });
        },
        
        
    });
});
