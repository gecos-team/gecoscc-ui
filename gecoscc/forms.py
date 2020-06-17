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

import os, errno, shutil
import time
import re
import colander
import deform
import logging
import zipfile

from pymongo import errors

from pkg_resources import resource_filename

from pyramid.threadlocal import get_current_registry

from chef.exceptions import ChefServerError
from deform.template import ZPTRendererFactory

from gecoscc import messages
from gecoscc.tasks import script_runner
from gecoscc.i18n import gettext as _
from gecoscc.utils import get_chef_api, create_chef_admin_user,\
    BASE_UPDATE_PATTERN
from gecoscc.socks import maintenance_mode
import traceback


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
                     'repeat_password', 'first_name', 'last_name')

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
            create_chef_admin_user(api, settings, admin_user['username'], None, admin_user['email'])
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
        self.children[self.sorted_fields.index('username')].widget.readonly = True

    def save(self, admin_user):
        if admin_user['password'] == '':
            del admin_user['password']
        self.collection.update({'username': self.username},
                               {'$set': admin_user})
        if admin_user['username'] != self.username and self.request.session['auth.userid'] == self.username:
            self.request.session['auth.userid'] = admin_user['username']
        self.created_msg(_('User edited successfully'))

class PermissionsForm(GecosForm):

    def save(self, permissions):
        ''' Saving permissions '''

        (ou_managed, ou_availables, ou_remote, ou_readonly) = (set(), set(), set(), set())

        for p in permissions:

            ou_selected = p['ou_selected'][0]

            if 'MANAGE' in p['permission']:
                ou_managed.add(ou_selected)
            if 'LINK' in p['permission']:
                ou_availables.add(ou_selected)
            if 'READONLY' in p['permission']:
                ou_readonly.add(ou_selected)
            if 'REMOTE' in p['permission']:
                ou_remote.add(ou_selected)
                if 'MANAGE' not in p['permission']:
                    ou_readonly.add(ou_selected)

        logger.debug("PermissionsForm ::: save - ou_managed = {}".format(ou_managed))
        logger.debug("PermissionsForm ::: save - ou_availables = {}".format(ou_availables))
        logger.debug("PermissionsForm ::: save - ou_remote = {}".format(ou_remote))
        logger.debug("PermissionsForm ::: save - ou_readonly = {}".format(ou_readonly))

        self.collection.update(
            {'username': self.username},
            {'$set': {
                'ou_managed': list(ou_managed),
                'ou_availables': list(ou_availables),
                'ou_remote': list(ou_remote),
                'ou_readonly': list(ou_readonly)
                }
            }
        )
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
            for _i, fileout in enumerate(self.schema.get_config_files('w', self.username)):
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


class UpdateForm(GecosForm):
    ''' Class for update form
    
    '''
    def validate(self, data):
        data_dict = dict(data)
        logger.debug("forms.py ::: UpdateForm - data = {0}".format(data_dict))
        return super(UpdateForm, self).validate(data)
    def save(self, update):
        settings = get_current_registry().settings
        update = update['local_file'] if update['local_file'] is not None else update['remote_file']
        sequence = re.match(BASE_UPDATE_PATTERN, update['filename']).group(1)
        logger.debug("forms.py ::: UpdateForm - sequence = %s" % sequence)
        # Updates directory: /opt/gecoscc/updates/<sequence>
        updatesdir = settings['updates.dir'] + sequence
        logger.debug("forms.py ::: UpdateForm - updatesdir = %s" % updatesdir)
        # Update zip file
        zipped = settings['updates.tmp'] + update['filename']
        logger.debug("forms.py ::: UpdateForm - zipped = %s" % zipped)
        try:
            # https://docs.python.org/2/library/shutil.html
            # The destination directory, named by dst, must not already exist; it will be created as well as missing parent directories
            # Checking copytree NFS
            shutil.copytree(update['decompress'], updatesdir)
            shutil.rmtree(update['decompress'])
            # Move zip file to updates dir
            shutil.move(zipped, updatesdir)

            # Decompress cookbook zipfile
            cookbookdir = settings['updates.cookbook'].format(sequence)
            logger.debug("forms.py ::: UpdateForm - cookbookdir = %s" % cookbookdir)
            for cookbook in os.listdir(cookbookdir):
                cookbook = cookbookdir + os.sep + cookbook
                logger.debug("forms.py ::: UpdateForm - cookbook = %s" % cookbook)
                if zipfile.is_zipfile(cookbook):
                    zip_ref = zipfile.ZipFile(cookbook,'r')
                    zip_ref.extractall(cookbookdir + os.sep + settings['chef.cookbook_name'])
                    zip_ref.close()
            # Insert update register
            self.request.db.updates.insert({'_id': sequence, 'name': update['filename'], 'path': updatesdir, 'timestamp': int(time.time()), 'rollback':0, 'user': self.request.user['username']})
            # Launching task for script execution
            script_runner.delay(self.request.user, sequence)
            link = '<a href="' +  self.request.route_url('updates_tail',sequence=sequence) + '">' + _("here") + '</a>'
            self.created_msg(_("Update log. %s") % link)
        except OSError as e:
            if e.errno == errno.EACCES:
                self.created_msg(_('Permission denied: %s') % updatesdir, 'danger')
            else:
                self.created_msg(_('There was an error attempting to upload an update. Please contact an administrator'), 'danger')
                
            logger.error("forms.py ::: UpdateForm - - " + \
                "error saving update: %s"%(str(e)))
            logger.error("Traceback: %s"%(traceback.format_exc()))
                      
        except (IOError, os.error) as e:
            logger.error("forms.py ::: UpdateForm - - " + \
                "error saving update: %s"%(str(e)))
            logger.error("Traceback: %s"%(traceback.format_exc()))
                       
        except errors.DuplicateKeyError as e:
            logger.error('Duplicate key error')
            self.created_msg(_('There was an error attempting to upload an update. Please contact an administrator'), 'danger')

class MaintenanceForm(GecosForm):
    css_class = 'deform-maintenance'

    def __init__(self, schema, request, *args, **kwargs):
        self.request = request
        buttons = (GecosButton(title=_('Submit'),
                               css_class='deform-maintenance-submit'),)

        super(MaintenanceForm, self).__init__(schema, buttons=buttons, *args, **kwargs)

    def save(self, postvars):
        logger.debug("forms.py ::: MaintenanceForm - postvars = {0}".format(postvars))

        if postvars['maintenance_message'] == "":
            logger.debug("forms.py ::: MaintenanceForm - Deleting maintenance message")
            self.request.db.settings.remove({'key':'maintenance_message'})
            self.created_msg(_('Maintenance message was deleted successfully.'))
        else:
            logger.debug("forms.py ::: MaintenanceForm - Creating maintenance message")
            compose = postvars['maintenance_message']
            maintenance_mode(self.request, compose)
            msg = self.request.db.settings.find_one({'key':'maintenance_message'})
            if msg is None:
                msg = {'key':'maintenance_message', 'value': compose, 'type':'string'}
                self.request.db.settings.insert(msg)
            else:
                self.request.db.settings.update({'key':'maintenance_message'},{'$set':{ 'value': compose}})

            self.request.session['maintenance_message'] = compose
            self.created_msg(_('Maintenance settings saved successfully.'))
