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


class FileBrowser(GPOConversor):

    policy = None

    def __init__(self, db):
        super(FileBrowser, self).__init__(db)
        self.policy = self.db.policies.find_one({'slug': 'file_browser_res'})

    def convert(self, xmlgpo):
        if self.policy is None:
            return None

        result = [{
            'policies': [],
            'guids': [],
        }]

        # Init values from GPO
        click_policy = 'single'
        confirm_trash = True
        default_folder_viewer = 'icon-view'
        show_hidden_files = True
        show_search_icon_toolbar = True

        # Get click_policy
        nodes = self.getNodesFromPath(xmlgpo, ['Computer', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])
        for node in nodes:
            if '@name' in node and node['@name'] == 'ClassicShell' and node['@value'] is not None:
                click_policy = 'single' if int(node['@value'], 16) == 1 else 'double'
        nodes = self.getNodesFromPath(xmlgpo, ['User', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])
        for node in nodes:
            if '@name' in node and node['@name'] == 'ClassicShell' and node['@value'] is not None:
                click_policy = 'single' if int(node['@value'], 16) == 1 else 'double'

        # Get confirm_trash
        nodes = self.getNodesFromPath(xmlgpo, ['Computer', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])
        for node in nodes:
            if '@name' in node and node['@name'] == 'ConfirmFileDelete' and node['@value'] is not None:
                confirm_trash = True if int(node['@value'], 16) == 1 else False
        nodes = self.getNodesFromPath(xmlgpo, ['User', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])
        for node in nodes:
            if '@name' in node and node['@name'] == 'ConfirmFileDelete' and node['@value'] is not None:
                confirm_trash = True if int(node['@value'], 16) == 1 else False

        # Get show_hidden_files
        nodes = self.getNodesFromPath(xmlgpo, ['User', 'ExtensionData', 'Extension', 'FolderOptions', 'GlobalFolderOptions', 'Properties'])
        for node in nodes:
            if '@hidden' in node:
                show_hidden_files = True if node['@hidden'] is 'SHOW' else False
        nodes = self.getNodesFromPath(xmlgpo, ['Computer', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])
        for node in nodes:
            if '@name' in node and node['@name'] == 'Hidden' and node['@value'] is not None:
                show_hidden_files = True if int(node['@value'], 16) == 1 else False
        nodes = self.getNodesFromPath(xmlgpo, ['User', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])
        for node in nodes:
            if '@name' in node and node['@name'] == 'Hidden' and node['@value'] is not None:
                show_hidden_files = True if int(node['@value'], 16) == 1 else False
        nodes = self.getNodesFromPath(xmlgpo, ['Computer', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])
        for node in nodes:
            if '@name' in node and node['@name'] == 'ShowSuperHidden' and node['@value'] is not None:
                show_hidden_files = True if int(node['@value'], 16) == 1 else False
        nodes = self.getNodesFromPath(xmlgpo, ['User', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])
        for node in nodes:
            if '@name' in node and node['@name'] == 'ShowSuperHidden' and node['@value'] is not None:
                show_hidden_files = True if int(node['@value'], 16) == 1 else False

        # Get show_search_icon_toolbar
        nodes = self.getNodesFromPath(xmlgpo, ['Computer', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])
        for node in nodes:
            if '@name' in node and node['@name'] == 'NoShellSearchButton' and node['@value'] is not None:
                show_search_icon_toolbar = True if int(node['@value'], 16) == 1 else False
        nodes = self.getNodesFromPath(xmlgpo, ['User', 'ExtensionData', 'Extension', 'RegistrySettings', 'Registry', 'Properties'])
        for node in nodes:
            if '@name' in node and node['@name'] == 'NoShellSearchButton' and node['@value'] is not None:
                show_search_icon_toolbar = True if int(node['@value'], 16) == 1 else False

        # Generate GECOSCC Policies
        result[0]['policies'] = [
            {
                str(self.policy['_id']): {
                    'click_policy': click_policy,
                    'confirm_trash': confirm_trash,
                    'default_folder_viewer': default_folder_viewer,
                    'show_hidden_files': show_hidden_files,
                    'show_search_icon_toolbar': show_search_icon_toolbar
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
