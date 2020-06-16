/*
* Copyright 2017, Junta de Andalucia
* http://www.juntadeandalucia.es/
*
* Authors:
*   Abraham Macias <amacias@solutia-it.es>
*
* All rights reserved - EUPL License V 1.1
* https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
*/

function calculateVersions(node, query) {
    var package_name = $(node.parentNode.children[0].el).find("input").last().val();
    //console.log('package_name is: '+package_name+" query.term:"+query.term);
    
    $.ajax({
        url: '/api/packages/',
        dataType: 'json',
        id : function (node) {
            return node._id;
        },
        data:  {
            package_name: package_name
        },
        type: 'GET',
        success: function(data) {
            if (jQuery.type(node.schemaElement.enum) === "undefined")
                node.schemaElement.enum = [];
            
            if (jQuery.inArray('latest', node.schemaElement.enum) < 0)
                node.schemaElement.enum.push('latest');
            
            if (jQuery.inArray('current', node.schemaElement.enum) < 0)
                node.schemaElement.enum.push('current');
        
            var options = [];
            var versions = [];
            options.push( {
                text: gettext('latest'),
                value: 'latest',
                id: 'latest'
            });      
            options.push( {
                text: gettext('current'),
                value: 'current',
                id: 'current'
            });    
            
            if(query.term.length > 0){
                options.push({id: query.term, text: query.term, value: query.term });
                node.schemaElement.enum.push(query.term);
            }
            
            
            if (jQuery.type(data) !== "undefined" && data.name == package_name) {
                // Check repositories
                for (var i = 0; i<data.repositories.length; i++) {
                    var repo = data.repositories[i];
                    
                    // Check architectures
                    for (var j = 0; j<repo.architectures.length; j++) {
                        var arch = repo.architectures[j];
                        
                        // Check versions
                        for (var k = 0; k<arch.versions.length; k++) {
                            var ver = arch.versions[k];
                            
                            if ( jQuery.inArray(ver.version, node.schemaElement.enum) < 0 ) {
                                node.schemaElement.enum.push(ver.version);
                            }
                            
                            var this_option = {
                                    text: ver.version,
                                    value: ver.version,
                                    id: ver.version
                                };
                            
                            if ( jQuery.inArray(ver.version, versions) < 0 ) {
                                options.push( this_option );
                                versions.push( ver.version );
                            }
                            
                        }                        
                        
                    }
                    
                    
                }
                
            }
            
            
            query.callback({results: options, more: false});

        },
        error: function(xhr, textStatus, error){
            if (xhr.status === 403) {
                forbidden_access();
            }
            else {
                console.log('Error: '+xhr.status+' '+xhr.statusText+' - '+textStatus+" - "+error);
            }
        }
    });
    
}

function calculateProviders(node, query) {
    var country = $(node.parentNode.children[0].el).find("input").last().val();
    console.log('country is: ' + country + " query.term:" + query.term);
    
    $.ajax({
        url: '/api/serviceproviders/',
        dataType: 'json',
        id : function (node) {
            return node._id;
        },
        data:  {
            name: country
        },
        type: 'GET',
        success: function(data) {
            if (jQuery.type(node.schemaElement.enum) === "undefined")
                node.schemaElement.enum = [];
            
            var providers = [];
          
            for (var i = 0; i<data.serviceproviders.length; i++) {
                var provider = {
                    text: data.serviceproviders[i]["provider"],
                    value: data.serviceproviders[i]["provider"],
                    id: data.serviceproviders[i]["provider"]
                };
                providers.push(provider);
                node.schemaElement.enum.push(provider);
            }
            
            query.callback({results: providers, more: false});
        },
        error: function(xhr, textStatus, error){
            if (xhr.status === 403) {
                forbidden_access();
            }
            else {
                console.log('Error: '+xhr.status+' '+xhr.statusText+' - '+textStatus+" - "+error);
            }
        }        
    });
    
}
