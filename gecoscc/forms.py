import deform

from pkg_resources import resource_filename

from deform.template import ZPTRendererFactory

from gecoscc.i18n import TranslationString as _


default_dir = resource_filename('deform', 'templates/')
gecoscc_dir = resource_filename('gecoscc', 'templates/deform/')
gecos_renderer = ZPTRendererFactory((gecoscc_dir, default_dir))


class GecosForm(deform.Form):

    template = 'form'
    item_template = 'mapping_item'
    css_class = 'deform'
    default_renderer = gecos_renderer
    sorted_fields = None

    def __init__(self, schema, action='', method='POST', buttons=(),
                 formid='deform', use_ajax=False, ajax_options='{}',
                 autocomplete=None, **kw):
        if not buttons:
            buttons = (deform.Button(title=_('Submit'),
                                     css_class='pull-right'),)
        if self.sorted_fields:
            schema.children.sort(key=lambda item: self.sorted_fields.index(item.name))
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


class BaseAdminUserForm(GecosTwoColumnsForm):

    sorted_fields = ('username', 'email', 'password',
                     'repeat_password', 'first_name', 'last_name')

    def __init__(self, schema, collection, username, request, *args, **kwargs):
        self.collection = collection
        self.username = username
        self.request = request
        super(BaseAdminUserForm, self).__init__(schema, *args, **kwargs)
        schema.children[self.sorted_fields.index('username')].ignore_unique = self.ignore_unique
        schema.children[self.sorted_fields.index('email')].ignore_unique = self.ignore_unique

    def created_msg(self, msg):
        if not 'messages' in self.request.session:
            self.request.session['messages'] = []
        self.request.session['messages'].append(('success', msg))


class AdminUserAddForm(BaseAdminUserForm):

    ignore_unique = False

    def save(self, admin_user):
        self.collection.insert(admin_user)
        self.created_msg(_('User created successfully'))


class AdminUserEditForm(BaseAdminUserForm):

    ignore_unique = True

    def __init__(self, schema, collection, *args, **kwargs):
        super(AdminUserEditForm, self).__init__(schema, collection, *args, **kwargs)
        schema.children[self.sorted_fields.index('password')] = schema.children[self.sorted_fields.index('password')].clone()
        schema.children[self.sorted_fields.index('repeat_password')] = schema.children[self.sorted_fields.index('repeat_password')].clone()
        schema.children[self.sorted_fields.index('password')].missing = ''
        schema.children[self.sorted_fields.index('repeat_password')].missing = ''

    def save(self, admin_user):
        if admin_user['password'] == '':
            del admin_user['password']
        self.collection.update({'username': self.username},
                               {'$set': admin_user})
        if admin_user['username'] != self.username and self.request.session['auth.userid'] == self.username:
            self.request.session['auth.userid'] = admin_user['username']
        self.created_msg(_('User edited successfully'))
