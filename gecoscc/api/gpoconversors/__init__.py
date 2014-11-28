# -*- coding: utf-8 -*-
"""
Copyright (c) 2013 Junta de Andalucia <http://www.juntadeandalucia.es> Licensed under the EUPL V.1.1
"""

from gecoscc.utils import get_domain

__all__ = ['desktop_background', 'sharing_permissions', 'automatic_updates', 'file_browser', 'user_mount', 'shutdown_options']


class GPOConversor(object):

    collection_name = 'nodes'

    xml_sid_guid = None

    def __init__(self, db):
        self.db = db
        self.collection = self.db[self.collection_name]

    def get_guid_from_sid(self, sid):
        for item in self.xml_sid_guid['items']['item']:
            if item['@sid'] == sid:
                return item['@guid']
        return None

    def _saveMongoADObject(self, mongoObject):
        if '_id' not in mongoObject.keys():
            # Insert object
            return self.collection.insert(mongoObject)
        else:
            # Update object
            return self.collection.update({'adObjectGUID': mongoObject['adObjectGUID']}, mongoObject)

    def getNodesFromPath(self, lst, path):

        subPath = list(path)
        nodename = subPath.pop(0)

        # Get node from lst by nodename
        node = lst[nodename] if nodename in lst else None
        if node is None:
            return []

        if len(subPath) == 0:
            return node if isinstance(node, list) else [node]
        else:
            if not isinstance(node, list):
                node = [node]
            result = []
            for subNode in node:
                result += self.getNodesFromPath(subNode, subPath)
            return result

    def apply(self, xmlgpo):
        result = True
        converted = self.convert(xmlgpo)
        if converted is None:
            # TODO: Inform about the problem
            return False
        for entry in converted:
            if result is False:
                break
            for guid in entry['guids']:
                if result is False:
                    break
                node = self.collection.find_one({'adObjectGUID': guid})
                domain = get_domain(node, self.collection)
                if node is None:
                    result = False
                    # TODO: Inform about the problem
                    continue
                for policy in entry['policies']:
                    policy_id = policy.keys()[0]
                    if policy_id not in domain.get('master_policies', {}) and node.get('policies', {}).get(policy_id, None):
                        continue
                    node['policies'][policy_id] = policy[policy_id]
                result = self._saveMongoADObject(node)
        return result
