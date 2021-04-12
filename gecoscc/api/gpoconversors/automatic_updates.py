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


class AutomaticUpdates(GPOConversor):

    policy = None

    def __init__(self, db):
        super(AutomaticUpdates, self).__init__(db)
        self.policy = self.db.policies.find_one({'slug': 'auto_updates_res'})

    def convert(self, xmlgpo):
        if self.policy is None:
            return None

        result = [{
            'policies': [],
            'guids': [],
        }]

        # Get value from GPO
        day = '*'
        hour = '*'
        minute = '*'

        nodes = self.getNodesFromPath(xmlgpo, ['Computer', 'ExtensionData', 'Extension', 'Policy'])  # Get value from policy
        for node in nodes:
            if 'Name' in node and node['Name'] == 'Configurar Actualizaciones automáticas' and node['State'] == 'Enabled':
                for dropDownList in node['DropDownList']:
                    if 'Name' not in dropDownList:
                        continue
                    if dropDownList['Name'] == 'Día de instalación programado: ' and dropDownList['State'] == 'Enabled':
                        day = dropDownList['Value']['Name'][0:1]
                        if day == '0':
                            day = '*'
                    if dropDownList['Name'] == 'Hora de instalación programada:' and dropDownList['State'] == 'Enabled':
                        hour = dropDownList['Value']['Name'][0:2]
                        minute = dropDownList['Value']['Name'][2:2]
                break

        # Generate GECOSCC Policies
        result[0]['policies'] = [
            {
                str(self.policy['_id']): {
                    'auto_updates_rules': {
                        'date': {
                            'month': '*',
                            'day': day,
                            'hour': hour,
                            'minute': minute
                        },
                        'days': [],
                        'onstart_update': False,
                        'onstop_update': False
                    }
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
