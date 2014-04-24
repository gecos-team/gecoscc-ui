from gecoscc.i18n import TranslationString as _

from . import BasePolicy


class RemoteStoragePolicy(BasePolicy):
    name = 'remote-storage'
    screen_name = _('Remote Storage')

    schema = {
        'type': 'object',
        'properties': {
            'name': {'type': 'string'},
            'node': {'type': 'string'},
            'storage_id': {'type': 'string'},
            'storage_node': {
                'type': 'object',
                'properties':  {
                    'memberof': {'type': 'array'},
                    'connection_string': {'type': 'string'},
                },
                'required': ['connection_string']
            }
        },
        'required': ['name', 'node', 'storage_id']
    }

    def translate_to_recipes(self):
        return {}
