import re

import colander
import deform
import os
import pyramid

from bson import ObjectId
from bson.objectid import InvalidId
from colander import null
from copy import copy

from deform.widget import FileUploadWidget, _normalize_choices, SelectWidget

from gecoscc.i18n import TranslationString as _
from gecoscc.utils import get_items_ou_children
from pyramid.threadlocal import get_current_registry

OU_ORDER = 1


class MemoryTmpStore(dict):

    def preview_url(self, name):
        return None

filestore = MemoryTmpStore()


class MyModel(object):
    pass

root = MyModel()


def get_root(request):
    return root


class ObjectIdField(object):

    def serialize(self, node, appstruct):
        if not appstruct or appstruct is colander.null:
            if isinstance(node.missing, colander._drop):
                return colander.drop
            return colander.null
        if not isinstance(appstruct, ObjectId):
            raise colander.Invalid(node, '{0} is not a ObjectId'.format(
                appstruct))
        return unicode(appstruct)

    def deserialize(self, node, cstruct):
        if not cstruct or cstruct is colander.null:
            if isinstance(node.missing, colander._drop):
                return colander.drop
            return colander.null
        try:
            return ObjectId(cstruct)
        except InvalidId:
            raise colander.Invalid(node, '{0} is not a valid id'.format(
                cstruct))
        except TypeError:
            raise colander.Invalid(node, '{0} is not a objectid string'.format(
                cstruct))

    def cstruct_children(self, node, cstruct):
        return []


class Unique(object):
    err_msg = _('There is some object with this value: ${val}')

    def __init__(self, collection, err_msg=None):
        self.collection = collection
        if err_msg:
            self.err_msg = err_msg

    def __call__(self, node, value):
        ignore_unique = getattr(node, 'ignore_unique', False)
        if ignore_unique:
            return
        request = pyramid.threadlocal.get_current_request()
        from gecoscc.db import get_db
        mongodb = get_db(request)
        if mongodb.adminusers.find({node.name: value}).count() > 0:
            err_msg = _(self.err_msg, mapping={'val': value})
            node.raise_invalid(err_msg)


class LowerAlphaNumeric(object):
    err_msg = _('Only lowercase letters or numbers')
    regex = re.compile(r'^([a-z]|[0-9])*$')

    def __call__(self, node, value):
        if not self.regex.match(value):
            node.raise_invalid(self.err_msg)


class URLExtend(object):
    err_msg = _('Invalid URL')
    regex = re.compile(r'^(https?|ftp|file)://[-A-Za-z0-9+&@#/%?=~_|!:,.;]+[-A-Za-z0-9+&@#/%=~_|]$')

    def __call__(self, node, value):
        if not self.regex.match(value):
            node.raise_invalid(self.err_msg)


class AdminUserValidator(object):

    def __call__(self, node, value):
        if value['password'] != value['repeat_password']:
            node.raise_invalid(_('The passwords do not match'))
        from gecoscc.userdb import create_password
        if bool(value['password']):
            value['password'] = create_password(value['password'])
        del value['repeat_password']


class Node(colander.MappingSchema):
    _id = colander.SchemaNode(ObjectIdField())
    path = colander.SchemaNode(colander.String())
    type = colander.SchemaNode(colander.String())
    lock = colander.SchemaNode(colander.Boolean(),
                               default=False)
    source = colander.SchemaNode(colander.String())
    name = colander.SchemaNode(colander.String())


class Nodes(colander.SequenceSchema):
    nodes = Node()


class ObjectIdList(colander.SequenceSchema):
    item = colander.SchemaNode(ObjectIdField(),
                               default=[],
                               missing=[])


class StringList(colander.SequenceSchema):
    item = colander.SchemaNode(colander.String(),
                               default=[],
                               missing=[])


class Group(Node):

    # Group object members
    # groupmembers = ObjectIdList(missing=[], default=[])

    # Node objects
    members = ObjectIdList(missing=[], default=[])

    memberof = ObjectIdList(missing=[], default=[])
    policies = colander.SchemaNode(colander.Mapping(unknown='preserve'),
                                   default={},
                                   missing={})


class Groups(colander.SequenceSchema):
    groups = Group()


class BaseUser(colander.MappingSchema):
    first_name = colander.SchemaNode(colander.String(),
                                     title=_('First name'),
                                     default='',
                                     missing='')
    last_name = colander.SchemaNode(colander.String(),
                                    title=_('Last name'),
                                    default='',
                                    missing='')


class User(Node, BaseUser):
    email = colander.SchemaNode(colander.String(),
                                validator=colander.Email())
    phone = colander.SchemaNode(colander.String(),
                                default='',
                                missing='')
    address = colander.SchemaNode(colander.String(),
                                  default='',
                                  missing='')
    memberof = ObjectIdList(missing=[], default=[])
    policies = colander.SchemaNode(colander.Mapping(unknown='preserve'),
                                   default={},
                                   missing={})
    computers = ObjectIdList(missing=[], default=[])


class Users(colander.SequenceSchema):
    users = User()


class ChainedSelectWidget(SelectWidget):

    null_value = ['']

    def get_select(self, mongodb, path, field_iter, html, **kw):
        for j, item_path in enumerate(path):
            readonly = kw.get('readonly', self.readonly)
            if item_path:
                values = get_items_ou_children(item_path, mongodb.nodes, 'ou')
                values = [(item['_id'], item['name']) for item in values]
                if not values:
                    continue
                values = [('', 'Select an Organisational Unit')] + values
                if j == len(path) - 1:
                    select_value = ''
                else:
                    select_value = path[j + 1]
            else:
                values = kw.get('values', self.values)
                select_value = item_path
            template = readonly and self.readonly_template or self.template
            kw['values'] = _normalize_choices(values)
            tmpl_values = self.get_template_values(field_iter, select_value, kw)
            html += field_iter.renderer(template, **tmpl_values)
        return html

    def serialize(self, field, cstruct, **kw):
        html = ""
        if cstruct in (null, None, []):
            cstruct = self.null_value
        request = pyramid.threadlocal.get_current_request()
        from gecoscc.db import get_db
        mongodb = get_db(request)
        for i, cstruct_item in enumerate(cstruct):
            field_iter = copy(field)
            if i > 0:
                field_iter.name = "%s-%s" % (field.name, i)

            if cstruct_item:
                ou = mongodb.nodes.find_one({'_id': ObjectId(cstruct_item)})
                if not ou:
                    continue
                path = ou['path'].split(',')
                path.append(cstruct_item)
            else:
                path = [cstruct_item]
            html += self.get_select(mongodb, path, field_iter, html, **kw)
            html += "<p></p>"
        if not html:
            html += self.get_select(mongodb, ['root'], field_iter, html, **kw)
        return html


@colander.deferred
def deferred_choices_widget(node, kw):
    choices = kw.get('ou_choices')
    return ChainedSelectWidget(values=choices)


class AdminUser(BaseUser):
    validator = AdminUserValidator()
    username = colander.SchemaNode(colander.String(),
                                   title=_('Username'),
                                   validator=colander.All(
                                       Unique('adminusers',
                                              _('There is a user with this username: ${val}')),
                                       LowerAlphaNumeric()))
    password = colander.SchemaNode(colander.String(),
                                   title=_('Password'),
                                   widget=deform.widget.PasswordWidget(),
                                   validator=colander.Length(min=6))
    repeat_password = colander.SchemaNode(colander.String(),
                                          default='',
                                          title=_('Repeat the password'),
                                          widget=deform.widget.PasswordWidget(),
                                          validator=colander.Length(min=6))
    email = colander.SchemaNode(colander.String(),
                                title=_('Email'),
                                validator=colander.All(
                                    colander.Email(),
                                    Unique('adminusers',
                                           _('There is a user with this email: ${val}'))))


class AdminUserOUManage(colander.MappingSchema):
    ou_managed = colander.SchemaNode(colander.List(),
                                     title=_('OU managed by this user'),
                                     widget=deferred_choices_widget)
    ou_availables = colander.SchemaNode(colander.List(),
                                        title=_('OU availables to register computers by this user'),
                                        widget=deferred_choices_widget)


class AdminUsers(colander.SequenceSchema):
    adminusers = AdminUser()


class AuthLDAPVariable(colander.MappingSchema):
    uri = colander.SchemaNode(colander.String(),
                              title=_('uri'),
                              default='URL_LDAP')
    base = colander.SchemaNode(colander.String(),
                               title=_('base'),
                               default='OU_BASE_USER')
    basegroup = colander.SchemaNode(colander.String(),
                                    title=_('base group'),
                                    default='OU_BASE_GROUP')
    binddn = colander.SchemaNode(colander.String(),
                                 title=_('binddn'),
                                 default='USER_WITH_BIND_PRIVILEGES')
    bindpwd = colander.SchemaNode(colander.String(),
                                  title=_('bindpwd'),
                                  default='PASSWORD_USER_BIND')


class ActiveDirectoryVariableNoSpecific(colander.MappingSchema):
    fqdn = colander.SchemaNode(colander.String(),
                               title=_('FQDN'))
    workgroup = colander.SchemaNode(colander.String(),
                                    title=_('WORKGROUP'))


class ActiveDirectoryVariableSpecific(colander.MappingSchema):
    sssd_conf = colander.SchemaNode(deform.FileData(),
                                    widget=FileUploadWidget(filestore),
                                    title=_('SSSD conf'))
    krb5_conf = colander.SchemaNode(deform.FileData(),
                                    widget=FileUploadWidget(filestore),
                                    title=_('KRB5 conf'))
    smb_conf = colander.SchemaNode(deform.FileData(),
                                   widget=FileUploadWidget(filestore),
                                   title=_('SMB conf'))
    pam_conf = colander.SchemaNode(deform.FileData(),
                                   widget=FileUploadWidget(filestore),
                                   title=_('PAM conf'))

AUTH_TYPE_CHOICES = (('LDAP', 'LDAP'),
                     ('AD', 'Active Directory'))


class AdminUserVariables(colander.MappingSchema):
    uri_ntp = colander.SchemaNode(colander.String(),
                                  default='URI_NTP_SERVER.EX',
                                  title=_('URI ntp'))
    auth_type = colander.SchemaNode(colander.String(),
                                    title=_('Auth type'),
                                    default='LDAP',
                                    widget=deform.widget.SelectWidget(values=AUTH_TYPE_CHOICES))
    specific_conf = colander.SchemaNode(colander.Boolean(),
                                        title=_('Specific conf'),
                                        default=False)
    auth_ldap = AuthLDAPVariable(title=_('Auth LDAP'))
    auth_ad = ActiveDirectoryVariableNoSpecific(title=_('Auth Active directory'))
    auth_ad_spec = ActiveDirectoryVariableSpecific(title=_('Auth Active directory'))

    def get_config_files(self, mode, username):
        return self.get_files(mode, username, ['sssd.conf', 'krb5.conf', 'smb.conf', 'pam.conf'])

    def get_files(self, mode, username, file_name):
        settings = get_current_registry().settings
        first_boot_media = settings.get('firstboot_api.media')
        user_media = os.path.join(first_boot_media, username)
        if mode == 'w' and not os.path.exists(user_media):
            os.makedirs(user_media)
        if isinstance(file_name, list):
            files = [open(os.path.join(user_media, name), mode) for name in file_name]
            return files
        return open(os.path.join(user_media, file_name), mode)


class OrganisationalUnit(Node):
    policies = colander.SchemaNode(colander.Mapping(unknown='preserve'),
                                   default={},
                                   missing={})
    extra = colander.SchemaNode(colander.String(),
                                default='',
                                missing='')
    node_order = colander.SchemaNode(colander.Integer(),
                                     default=OU_ORDER,
                                     missing=OU_ORDER)
    master = colander.SchemaNode(colander.String(),
                                 default='',
                                 missing='')
    master_policies = colander.SchemaNode(colander.Mapping(unknown='preserve'),
                                          default={},
                                          missing={})


class OrganisationalUnits(colander.SequenceSchema):
    organisationalunits = OrganisationalUnit()


COMPUTER_FAMILY = {
    'desktop': _('Desktop'),
    'laptop': _('Laptop'),
    'netbook': _('Netbook'),
    'tablet': _('Tablet'),
}


class Computer(Node):
    memberof = ObjectIdList(missing=[], default=[])
    family = colander.SchemaNode(colander.String(),
                                 default='desktop',
                                 validator=colander.OneOf(
                                     COMPUTER_FAMILY.keys()))
    registry = colander.SchemaNode(colander.String(),
                                   default='',
                                   missing='')
    serial = colander.SchemaNode(colander.String(),
                                 default='',
                                 missing='')
    policies = colander.SchemaNode(colander.Mapping(unknown='preserve'),
                                   default={},
                                   missing={})
    node_chef_id = colander.SchemaNode(colander.String(),
                                       default='',
                                       missing='')


class Computers(colander.SequenceSchema):
    computers = Computer()


PRINTER_TYPE = {
    'laser': _('Laser'),
    'ink': _('Ink'),
    'matrix': _('Dot matrix'),
}

PRINTER_CONN_TYPE = {
    'network': _('Network'),
    'local': _('Local'),
}


class Printer(Node):
    printtype = colander.SchemaNode(colander.String(),
                                    default='laser',
                                    validator=colander.OneOf(
                                        PRINTER_TYPE.keys()))
    manufacturer = colander.SchemaNode(colander.String())
    model = colander.SchemaNode(colander.String())
    serial = colander.SchemaNode(colander.String(),
                                 default='',
                                 missing='')
    registry = colander.SchemaNode(colander.String(),
                                   default='',
                                   missing='')
    description = colander.SchemaNode(colander.String(),
                                      default='',
                                      missing='')
    location = colander.SchemaNode(colander.String(),
                                   default='',
                                   missing='')
    connection = colander.SchemaNode(colander.String(),
                                     default='network',
                                     validator=colander.OneOf(
                                         PRINTER_CONN_TYPE.keys()))
    uri = colander.SchemaNode(colander.String())
    ppd_uri = colander.SchemaNode(colander.String(),
                                  default='',
                                  missing='',
                                  validator=URLExtend())


class Printers(colander.SequenceSchema):
    printers = Printer()


STORAGE_PROTOCOLS = {
    'ftp': _('FTP'),
    'sshfs': _('SSHFS'),
    'nfs': _('NFS'),
    'smb': _('SAMBA v3'),
    'smb4': _('SAMBA v4'),
}

STORAGE_MOUNT_TYPE = {
    'fstab': _('System mounts (fstab)'),
    'gvfs': _('User space mounts (gvfs)'),
}


class Storage(Node):
    uri = colander.SchemaNode(colander.String(),
                              default='')


class Storages(colander.SequenceSchema):
    storages = Storage()


class Repository(Node):
    uri = colander.SchemaNode(colander.String())
    components = StringList(missing=[], default=[])
    distribution = colander.SchemaNode(colander.String())
    deb_src = colander.SchemaNode(colander.Boolean(),
                                  default=False)
    repo_key = colander.SchemaNode(colander.String())
    key_server = colander.SchemaNode(colander.String())


class Repositories(colander.SequenceSchema):
    repositories = Repository()


JOB_STATUS = {
    # Calculating node changes
    'processing': _('Processing'),

    # The configurator is applying the changes
    'applying': _('Applying changes'),

    # All the changes were applied SUCCESSFULLY
    'finished': _('Changes applied'),

    # There was errors during the process
    'errors': _('There was errors'),
}


class Job(colander.MappingSchema):
    # This is not a ObjectId, is a UUID4 format string of numbers
    _id = colander.SchemaNode(colander.String())

    userid = colander.SchemaNode(ObjectIdField())
    objid = colander.SchemaNode(ObjectIdField())
    objname = colander.SchemaNode(colander.String(), default='no-provided')
    computerid = colander.SchemaNode(ObjectIdField(), missing=colander._drop())
    computername = colander.SchemaNode(colander.String(), default='no-provided')
    policyname = colander.SchemaNode(colander.String(), default='no-provided')
    administrator_username = colander.SchemaNode(colander.String(), default='no-provided')

    # Verify that the status selected already exists
    status = colander.SchemaNode(colander.String(),
                                 validator=colander.OneOf(JOB_STATUS.keys()))
    message = colander.SchemaNode(colander.String(),
                                  default='',
                                  missing='')
    type = colander.SchemaNode(colander.String())
    op = colander.SchemaNode(colander.String(),
                             validator=colander.OneOf(
                                 ['created', 'changed', 'deleted']))

    created = colander.SchemaNode(colander.DateTime())
    last_update = colander.SchemaNode(colander.DateTime())


class Jobs(colander.SequenceSchema):
    jobs = Job()


class Policy(colander.MappingSchema):
    _id = colander.SchemaNode(ObjectIdField())
    name = colander.SchemaNode(colander.String())
    slug = colander.SchemaNode(colander.String())
    schema = colander.SchemaNode(colander.Mapping(unknown='preserve'),
                                 default={},
                                 missing={})
    targets = StringList(missing=[], default=[])
    path = colander.SchemaNode(colander.String(),
                               default='',
                               missing='')
    is_emitter_policy = colander.SchemaNode(colander.Boolean(),
                                            default=False)
    support_os = StringList(missing=[], default=[])


class Policies(colander.SequenceSchema):
    policies = Policy()
