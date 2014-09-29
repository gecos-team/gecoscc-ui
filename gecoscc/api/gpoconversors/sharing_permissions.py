# -*- coding: utf-8 -*-
"""
Copyright (c) 2013 Junta de Andalucia <http://www.juntadeandalucia.es> Licensed under the EUPL V.1.1
"""

from gecoscc.api.gpoconversors import GPOConversor

class SharingPermissions(GPOConversor):
 
    policy = None;

    def __init__(self, db):
        super(SharingPermissions, self).__init__(db)
        self.policy = self.db.policies.find_one({'name':'Sharing permissions'});

    def convert(self, xmlgpo):
        if self.policy is None: return None

        result = [{
            'policies': [],
            'guids': [],
        }]

        # Get value from GPO
        can_share = False
        nodes = self.getNodesFromPath(xmlgpo, ['User', 'ExtensionData', 'Extension', 'Policy']) # Get value from policy
        for node in nodes:
            if 'Name' in node and node['Name'] == 'Impedir que los usuarios compartan archivos dentro de su perfil' and node['State'] is not None:
            	can_share = False if node['State'] != 'Enabled' else True
            	break
        nodes = self.getNodesFromPath(xmlgpo, ['Computer', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties']) # Get value from Computer Registry
        for node in nodes:
            if '@name' in node and node['@name'] == 'NoFileSharing' and node['@value'] is not None:
            	can_share = False if int(node['@value'], 16) == 1 else True
            	break
        nodes = self.getNodesFromPath(xmlgpo, ['User', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties']) # Get value from User Registry
        for node in nodes:
            if '@name' in node and node['@name'] == 'NoFileSharing' and node['@value'] is not None:
            	can_share = False if int(node['@value'], 16) == 1 else True
            	break

        # Generate GECOSCC Policies
        result[0]['policies'] = [
            {
                str(self.policy['_id']): {
                    'can_share': can_share
                }
            }
        ]

        # Get user GUID from SID
        nodes = self.getNodesFromPath(xmlgpo, ['SecurityDescriptor', 'Permissions', 'TrusteePermissions', 'Trustee', 'SID'])
        for node in nodes:
            guid = self.get_guid_from_sid(node['#text'])
            if guid is not None:
                result[0]['guids'].append(guid)

        return result
