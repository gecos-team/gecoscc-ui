from pyramid.i18n import get_localizer


class BaseView(object):

    def __init__(self, context, request):
        self.context = context
        self.request = request
        self.translate = get_localizer(self.request).translate
