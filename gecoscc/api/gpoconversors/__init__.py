# -*- coding: utf-8 -*-
"""
Copyright (c) 2013 Junta de Andalucia <http://www.juntadeandalucia.es> Licensed under the EUPL V.1.1
"""

__all__ = ['desktop_background', 'sharing_permissions', 'automatic_updates', 'file_browser', 'user_mount', 'shutdown_options']


class GPOConversor(object):

    mongoCollectionName = 'nodes'

    xml_sid_guid = None

    def __init__(self, db):
        self.db = db

    def get_guid_from_sid(self, sid):
        for item in self.xml_sid_guid['items']['item']:
            if item['@sid'] == sid:
                return item['@guid']
        return None

    def _saveMongoADObject(self, mongoObject):
        if '_id' not in mongoObject.keys():
            # Insert object
            return self.db[self.mongoCollectionName].insert(mongoObject)
        else:
            # Update object
            return self.db[self.mongoCollectionName].update({'adObjectGUID': mongoObject['adObjectGUID']}, mongoObject)

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
                node = self.db[self.mongoCollectionName].find_one({'adObjectGUID': guid})
                if node is None:
                    result = False
                    # TODO: Inform about the problem
                    continue
                for policy in entry['policies']:
                    node['policies'][policy.keys()[0]] = policy[policy.keys()[0]]
                result = self._saveMongoADObject(node)
        return result
