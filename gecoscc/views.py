from pyramid.i18n import TranslationStringFactory

_ = TranslationStringFactory('gecoscc')

def my_view(request):
    return {'project':'gecoscc'}
