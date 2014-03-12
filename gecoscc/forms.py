from pkg_resources import resource_filename

from deform import Button as DeButton
from deform import Form as DeForm
from deform.template import ZPTRendererFactory

from gecoscc.i18n import TranslationString as _


default_dir = resource_filename('deform', 'templates/')
gecoscc_dir = resource_filename('gecoscc', 'templates/deform/')
gecos_renderer = ZPTRendererFactory((gecoscc_dir, default_dir))


class GecosForm(DeForm):

    template = 'form'
    item_template = 'mapping_item'
    css_class = 'deform'
    default_renderer = gecos_renderer

    def __init__(self, schema, action='', method='POST', buttons=(),
                 formid='deform', use_ajax=False, ajax_options='{}',
                 autocomplete=None, **kw):
        if not buttons:
            buttons = (DeButton(title=_('Submit'), css_class='pull-right'),)
        super(GecosForm, self).__init__(schema, action=action,
                                        method=method,
                                        buttons=buttons,
                                        formid='deform',
                                        use_ajax=use_ajax,
                                        ajax_options=ajax_options,
                                        autocomplete=None, **kw)
        self.widget.template = self.template
        self.widget.item_template = self.item_template
        self.widget.css_class = self.css_class


class GecosTwoColumnsForm(GecosForm):

    template = 'form_two_columns'
    item_template = 'mapping_item_two_columns'
    css_class = 'deform form-horizontal'


class AdminUserForm(GecosTwoColumnsForm):

    def __init__(self, schema, *args, **kwargs):
        password_field = schema.children.pop(-2)
        username_field = schema.children.pop(-2)
        schema.children = [username_field, password_field] + schema.children
        super(AdminUserForm, self).__init__(schema, *args, **kwargs)
