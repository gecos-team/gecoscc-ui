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


class ShutdownOptions(GPOConversor):

    policy = None

    def __init__(self, db):
        super(ShutdownOptions, self).__init__(db)
        self.policy = self.db.policies.find_one({'slug': 'shutdown_options_res'})

    def convert(self, xmlgpo):
        if self.policy is None:
            return None

        result = [{
            'policies': [],
            'guids': [],
        }]

        # Get value from GPO
        disable_log_out = False
        nodes = self.getNodesFromPath(xmlgpo, ['User', 'ExtensionData', 'Extension', 'Policy'])  # Get value from policy
        for node in nodes:
            if 'Name' in node and node['Name'] == u'Quitar Cerrar sesión' and node['State'] is not None:
                disable_log_out = True if node['State'] == 'Enabled' else False
                break
        nodes = self.getNodesFromPath(xmlgpo, ['Computer', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])  # Get value from Computer Registry
        for node in nodes:
            if '@name' in node and node['@name'] == 'NoLogOff' and node['@value'] is not None:
                disable_log_out = True if int(node['@value'], 16) == 1 else False
                break
        nodes = self.getNodesFromPath(xmlgpo, ['User', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])  # Get value from User Registry
        for node in nodes:
            if '@name' in node and node['@name'] == 'NoLogOff' and node['@value'] is not None:
                disable_log_out = True if int(node['@value'], 16) == 1 else False
                break

        # Generate GECOSCC Policies
        result[0]['policies'] = [
            {
                str(self.policy['_id']): {
                    'disable_log_out': disable_log_out
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
