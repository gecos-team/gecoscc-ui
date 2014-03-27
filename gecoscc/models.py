import colander
import deform
import pyramid
import simplejson as json

from bson import ObjectId
from bson.objectid import InvalidId

from gecoscc.i18n import TranslationString as _


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


class JsonSchemaField(object):
    """ Should validate if the json object is a valid json schema """

    def serialize(self, node, appstruct):
        if appstruct is colander.null:
            if isinstance(node.missing, colander._drop):
                return colander.drop
            return colander.null
        if not isinstance(appstruct, dict):
            raise colander.Invalid(node, '{0} is not a json schema'.format(
                appstruct))
        return json.dumps(appstruct)

    def deserialize(self, node, cstruct):
        if cstruct is colander.null:
            if isinstance(node.missing, colander._drop):
                return colander.drop
            return colander.null
        try:
            return json.loads(cstruct)
        except:
            raise colander.Invalid(node, '{0} is not a valid json '
                                   'object'.format(cstruct))

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
    identifier = colander.SchemaNode(colander.String(),
                                     default='',
                                     missing='')
    ip = colander.SchemaNode(colander.String(),
                             default='',
                             missing='')
    mac = colander.SchemaNode(colander.String(),
                              default='',
                              missing='')
    family = colander.SchemaNode(colander.String(),
                                 default='desktop',
                                 validator=colander.OneOf(
                                     COMPUTER_FAMILY.keys()
                                 ))
    serial = colander.SchemaNode(colander.String(),
                                 default='',
                                 missing='')
    registry = colander.SchemaNode(colander.String(),
                                   default='',
                                   missing='')
    extra = colander.SchemaNode(colander.String(),
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

PRINTER_DRIVER = {
    'auto': _('Automatic installation'),
    'manual': _('Manual installation'),
}

PRINTER_QUALITIES = {
    'low': _('Low'),
    'medium': _('Medium'),
    'high': _('High'),
    'ultra': _('Very high'),
}


class Printer(Node):
    printtype = colander.SchemaNode(colander.String(),
                                    default='laser',
                                    validator=colander.OneOf(
                                        PRINTER_TYPE.keys()
                                    ))
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
                                         PRINTER_CONN_TYPE.keys()
                                     ))
    printerpath = colander.SchemaNode(colander.String(),
                                      default='',
                                      missing='')
    driver = colander.SchemaNode(colander.String(),
                                 default='auto',
                                 validator=colander.OneOf(
                                     PRINTER_DRIVER.keys()
                                 ))
    driverBrand = colander.SchemaNode(colander.String(),
                                      default='',
                                      missing='')  # TODO choices?
    driverModel = colander.SchemaNode(colander.String(),
                                      default='',
                                      missing='')  # TODO choices?
    driverFile = colander.SchemaNode(colander.String(),
                                     default='',
                                     missing='')  # TODO url? host the file?
    memberof = ObjectIdList(missing=[], default=[])
    pageSize = colander.SchemaNode(colander.String(),
                                   default='',
                                   missing='')  # TODO choices?
    quality = colander.SchemaNode(colander.String(),
                                  default='auto',
                                  validator=colander.OneOf(
                                      PRINTER_QUALITIES.keys()
                                  ))
    paperTray = colander.SchemaNode(colander.String(),
                                    default='',
                                    missing='')  # TODO remove this field?
    duplex = colander.SchemaNode(colander.Boolean(),
                                 default=False)


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
    server = colander.SchemaNode(colander.String())
    port = colander.SchemaNode(colander.Integer(),
                               validator=colander.Range(min=1, max=65535),
                               default='',
                               missing='')
    protocol = colander.SchemaNode(colander.String(),
                                   validator=colander.OneOf(
                                       STORAGE_PROTOCOLS.keys()
                                   ))
    localpath = colander.SchemaNode(colander.String())
    mount = colander.SchemaNode(colander.String(),
                                validator=colander.OneOf(
                                    STORAGE_MOUNT_TYPE.keys()
                                ),
                                default='gvfs')
    extraops = colander.SchemaNode(colander.String(),
                                   default='',
                                   missing='')


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
                                 ['created', 'changed', 'deleted']
                             ))

    created = colander.SchemaNode(colander.DateTime())
    last_update = colander.SchemaNode(colander.DateTime())


class Jobs(colander.SequenceSchema):
    jobs = Job()
