# -*- coding: utf-8 -*-

#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Jose Luis Salvador <salvador.joseluis@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from gecoscc.api.gpoconversors import GPOConversor


class UserMount(GPOConversor):

    policy = None

    def __init__(self, db):
        super(UserMount, self).__init__(db)
        self.policy = self.db.policies.find_one({'slug': 'user_mount_res'})

    def convert(self, xmlgpo):
        if self.policy is None:
            return None

        result = [{
            'policies': [],
            'guids': [],
        }]

        # Get value from GPO
        can_mount = False
        nodes = self.getNodesFromPath(xmlgpo, ['User', 'ExtensionData', 'Extension', 'Policy'])  # Get value from policy
        for node in nodes:
            if 'Name' in node and node['Name'] == 'Quitar "Conectar a unidad de red" y "Desconectar de unidad de red"' and node['State'] is not None:
                can_mount = False if node['State'] != 'Enabled' else True
                break
        nodes = self.getNodesFromPath(xmlgpo, ['Computer', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])  # Get value from Computer Registry
        for node in nodes:
            if '@name' in node and node['@name'] == 'NoNetConnectDisconnect' and node['@value'] is not None:
                can_mount = False if int(node['@value'], 16) == 1 else True
                break
        nodes = self.getNodesFromPath(xmlgpo, ['User', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])  # Get value from User Registry
        for node in nodes:
            if '@name' in node and node['@name'] == 'NoNetConnectDisconnect' and node['@value'] is not None:
                can_mount = False if int(node['@value'], 16) == 1 else True
                break

        # Generate GECOSCC Policies
        result[0]['policies'] = [
            {
                str(self.policy['_id']): {
                    'can_mount': can_mount
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
