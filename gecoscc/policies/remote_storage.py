from gecoscc.i18n import TranslationString as _

from . import BasePolicy


class RemoteStoragePolicy(BasePolicy):
    name = 'remote-storage'
    screen_name = _('Remote Storage')

    def translate_to_recipes(self):
        return {}
