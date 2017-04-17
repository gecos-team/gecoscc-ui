#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Author:
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import os

import colander
import deform
import logging

from pkg_resources import resource_filename

from pyramid.threadlocal import get_current_registry

from chef.exceptions import ChefServerError
from deform.template import ZPTRendererFactory

from gecoscc import messages
from gecoscc.i18n import gettext as _
from gecoscc.utils import get_chef_api, create_chef_admin_user


default_dir = resource_filename('deform', 'templates/')
gecoscc_dir = resource_filename('gecoscc', 'templates/deform/')
gecos_renderer = ZPTRendererFactory((gecoscc_dir, default_dir))

logger = logging.getLogger(__name__)

class GecosButton(deform.Button):

    def __init__(self, name='_submit', title=None, type='submit', value=None,
                 disabled=False, css_class=None, attrs=None):
        super(GecosButton, self).__init__(name=name, title=title, type=type, value=value,
                                          disabled=False, css_class=css_class)
        self.attrs = attrs or {}


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
            buttons = (GecosButton(title=_('Submit'),
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

    def created_msg(self, msg, msg_type='success'):
        messages.created_msg(self.request, msg, msg_type)


class GecosTwoColumnsForm(GecosForm):

    template = 'form_two_columns'
    item_template = 'mapping_item_two_columns'
    css_class = 'deform form-horizontal'


class BaseAdminUserForm(GecosTwoColumnsForm):

    sorted_fields = ('username', 'email', 'password',
                     'repeat_password', 'first_name', 'last_name', 'authtype',
                     'ou_managed', 'ou_availables',)

    def __init__(self, schema, collection, username, request, *args, **kwargs):
        self.collection = collection
        self.username = username
        self.request = request
        super(BaseAdminUserForm, self).__init__(schema, *args, **kwargs)
        schema.children[self.sorted_fields.index('username')].ignore_unique = self.ignore_unique
        schema.children[self.sorted_fields.index('email')].ignore_unique = self.ignore_unique


class AdminUserAddForm(BaseAdminUserForm):

    ignore_unique = False

    def save(self, admin_user):
        self.collection.insert(admin_user)
        admin_user['plain_password'] = self.cstruct['password']
        settings = get_current_registry().settings
        user = self.request.user
        
        api = get_chef_api(settings, user)

        try:
            create_chef_admin_user(api, settings, admin_user['username'], None, admin_user['email'], admin_user['authtype'])
            self.created_msg(_('User created successfully'))
            return True
        except ChefServerError as e:
            self.created_msg(e.message, 'danger')
            self.collection.remove({'username': admin_user['username']})
            raise e


class AdminUserEditForm(BaseAdminUserForm):

    ignore_unique = True

    def __init__(self, schema, collection, *args, **kwargs):
        buttons = (GecosButton(title=_('Submit'),
                               css_class='pull-right',
                               name='_submit'),
                   GecosButton(title=_('Delete'),
                               name='_delete',
                               css_class='pull-right',
                               type='button'))
        super(AdminUserEditForm, self).__init__(schema, collection, buttons=buttons, *args, **kwargs)
        schema.children[self.sorted_fields.index('password')] = schema.children[self.sorted_fields.index('password')].clone()
        schema.children[self.sorted_fields.index('repeat_password')] = schema.children[self.sorted_fields.index('repeat_password')].clone()
        schema.children[self.sorted_fields.index('password')].missing = ''
        schema.children[self.sorted_fields.index('repeat_password')].missing = ''
        schema.children[self.sorted_fields.index('authtype')] = schema.children[self.sorted_fields.index('authtype')].clone()
        self.children[self.sorted_fields.index('username')].widget.readonly = True

    def save(self, admin_user):
        if admin_user['password'] == '':
            del admin_user['password']
        self.collection.update({'username': self.username},
                               {'$set': admin_user})
        if admin_user['username'] != self.username and self.request.session['auth.userid'] == self.username:
            self.request.session['auth.userid'] = admin_user['username']
        self.created_msg(_('User edited successfully'))


class AdminUserOUManageForm(GecosTwoColumnsForm):

    ou_managed_count = colander.SchemaNode(colander.Integer(),
                                           title='',
                                           name='ou_managed_count',
                                           widget=deform.widget.HiddenWidget(),
                                           default=1)
    ou_availables_count = colander.SchemaNode(colander.Integer(),
                                              title='',
                                              name='ou_availables_count',
                                              widget=deform.widget.HiddenWidget(),
                                              default=1)

    def __init__(self, schema, collection, username, request, *args, **kwargs):
        schema.get('ou_managed').title += '<p><a href="#ou-managed" class="add-another">%s</a></p>' % _('Add another')
        schema.get('ou_availables').title += '<p><a href="#ou-availables" class="add-another">%s</a></p>' % _('Add another')
        schema.children.append(self.ou_managed_count)
        schema.children.append(self.ou_availables_count)
        super(AdminUserOUManageForm, self).__init__(schema, collection=collection,
                                                    username=username, request=request,
                                                    *args, **kwargs)

    def save(self, ous_managed):
        self.collection.update({'username': self.username},
                               {'$set': ous_managed})
        self.created_msg(_('User edited successfully'))


class AdminUserVariablesForm(GecosForm):

    def validate(self, data):
        data_dict = dict(data)
        if data_dict['auth_type'] == 'LDAP':
            for field in self.schema.get('auth_ad').children:
                field.missing = ''
            for field in self.schema.get('auth_ad_spec').children:
                field.validator = None
                field.missing = ''
        else:
            for field in self.schema.get('auth_ldap').children:
                field.missing = ''
            if data_dict.get('specific_conf', False):
                for field in self.schema.get('auth_ad').children:
                    field.validator = None
                    field.missing = ''
            else:
                for field in self.schema.get('auth_ad_spec').children:
                    field.validator = None
                    field.missing = ''
        return super(AdminUserVariablesForm, self).validate(data)

    def save(self, variables):
        if variables['auth_type'] != 'LDAP' and variables.get('specific_conf', False):
            for i, fileout in enumerate(self.schema.get_config_files('w', self.username)):
                fileout_name = fileout.name.split(os.sep)[-1]
                file_field = variables['auth_ad_spec'][fileout_name.replace('.', '_')]
                if not file_field:
                    continue
                filein = file_field['fp']
                fileout.write(filein.read())
                filein.close()
                fileout.close()
        del variables['auth_ad_spec']
        self.collection.update({'username': self.username}, {'$set': {'variables': variables}})
        self.created_msg(_('Variables updated successfully'))
