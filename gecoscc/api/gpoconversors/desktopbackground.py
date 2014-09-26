# -*- coding: utf-8 -*-
"""
Copyright (c) 2013 Junta de Andalucia <http://www.juntadeandalucia.es> Licensed under the EUPL V.1.1
"""

import re

from gecoscc.api.gpoconversors import GPOConversor

class DesktopBackground(GPOConversor):

    policy = None;

    def __init__(self, db):
        super(DesktopBackground, self).__init__(db)
        self.policy = self.db.policies.find_one({'name':'Desktop Background'});

    def convert(self, xmlgpo):
        if self.policy is None: return None

        result = [{
            'policies': [],
            'guids': [],
        }]

        # Find into XmlGPO the wallpaper policy
        wallpaper_url = None
        nodes = self.getNodesFromPath(xmlgpo, ['Computer', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])
        for node in nodes:
            if '@name' in node and node['@name'] == 'Wallpaper' and node['@value'] is not None:
                wallpaper_url = node['@value']

        if wallpaper_url is None:
            return result

        # Convert wallpaper url from Windows to Linux
        wallpaper_url = wallpaper_url \
            .replace('\\\\', '//') \
            .replace('\\', '/')
        wallpaper_url = re.sub(r'^([a-zA-Z]):\/?(.+)', lambda pat: "/" + pat.group(1).lower() + "/" + pat.group(2), wallpaper_url)

        # Generate GECOSCC Policies
        result[0]['policies'] = [
            {
                str(self.policy['_id']): {
                    'desktop_file': wallpaper_url
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
