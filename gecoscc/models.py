import colander
import deform
import os
import pyramid

from bson import ObjectId
from bson.objectid import InvalidId

from deform.widget import FileUploadWidget

from gecoscc.i18n import TranslationString as _
from pyramid.threadlocal import get_current_registry


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


class Users(colander.SequenceSchema):
    users = User()


class AdminUser(BaseUser):
    validator = AdminUserValidator()
    username = colander.SchemaNode(colander.String(),
                                   title=_('Username'),
                                   validator=Unique('adminusers',
                                                    _('There is a user with this username: ${val}')))
    password = colander.SchemaNode(colander.String(),
                                   title=_('Password'),
                                   widget=deform.widget.PasswordWidget())
    repeat_password = colander.SchemaNode(colander.String(),
                                          default='',
                                          title=_('Repeat the password'),
                                          widget=deform.widget.PasswordWidget())
    email = colander.SchemaNode(colander.String(),
                                title=_('Email'),
                                validator=colander.All(
                                    colander.Email(),
                                    Unique('adminusers',
                                           _('There is a user with this email: ${val}'))))


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
                                  default='http://URL_NTP_SERVER',
                                  title=_('URI ntp'))
    chef_server_uri = colander.SchemaNode(colander.String(),
                                          title=_('Chef server uri'),
                                          default='https://URL_CHEF')
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
    registry = colander.SchemaNode(colander.String(),
                                   default='',
                                   missing='')
    policies = colander.SchemaNode(colander.Mapping(unknown='preserve'),
                                   default={},
                                   missing={})


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
    brand = colander.SchemaNode(colander.String(),
                                default='',
                                missing='')
    model = colander.SchemaNode(colander.String(),
                                default='',
                                missing='')
    serial = colander.SchemaNode(colander.String(),
                                 default='',
                                 missing='')
    registry = colander.SchemaNode(colander.String(),
                                   default='',
                                   missing='')
    name = colander.SchemaNode(colander.String(),
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
    printerpath = colander.SchemaNode(colander.String(),
                                      default='',
                                      missing='')
    driverFile = colander.SchemaNode(colander.String(),
                                     default='',
                                     missing='')  # TODO url? host the file?
    memberof = ObjectIdList(missing=[], default=[])


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
    memberof = ObjectIdList(missing=[], default=[])
    connection_string = colander.SchemaNode(colander.String(),
                                            default='')


class Storages(colander.SequenceSchema):
    storages = Storage()


class Repository(Node):
    url = colander.SchemaNode(colander.String())
    description = colander.SchemaNode(colander.String(),
                                      default='',
                                      missing='')


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

    # Verify that the status selected already exists
    status = colander.SchemaNode(colander.String(),
                                 validator=colander.OneOf(JOB_STATUS.keys()))
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
    schema = colander.SchemaNode(colander.Mapping(unknown='preserve'),
                                 default={},
                                 missing={})
    targets = StringList(missing=[], default=[])


class Policies(colander.SequenceSchema):
    policies = Policy()
