from bson import ObjectId
from bson.objectid import InvalidId

import colander

from gecoscc.i18n import TranslationString as _


class MyModel(object):
    pass

root = MyModel()


def get_root(request):
    return root


class ObjectIdField(object):

    def serialize(self, node, appstruct):
        if appstruct is colander.null:
            if isinstance(node.missing, colander._drop):
                return colander.drop
            return colander.null
        if not isinstance(appstruct, ObjectId):
            raise colander.Invalid(node, '{0} is not a ObjectId'.format(
                appstruct))
        return unicode(appstruct)

    def deserialize(self, node, cstruct):
        if cstruct is colander.null:
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


class Node(colander.MappingSchema):
    _id = colander.SchemaNode(ObjectIdField())
    path = colander.SchemaNode(colander.String())
    type = colander.SchemaNode(colander.String())
    lock = colander.SchemaNode(colander.Boolean(),
                               default=False)
    source = colander.SchemaNode(colander.String())
    name = colander.SchemaNode(colander.String())

    # Group objects
    memberof = colander.Seq(ObjectIdField())


class Nodes(colander.SequenceSchema):
    nodes = Node()


class ObjectIdList(colander.SequenceSchema):
    item = colander.SchemaNode(ObjectIdField(),
                               default=[],
                               missing=[])


class Group(Node):

    # Group object members
    groupmembers = ObjectIdList(missing=[], default=[])

    # Node objects
    nodemembers = ObjectIdList(missing=[], default=[])


class Groups(colander.SequenceSchema):
    groups = Group()


class User(Node):
    email = colander.SchemaNode(colander.String())
    first_name = colander.SchemaNode(colander.String(),
                                     default='',
                                     missing='')
    last_name = colander.SchemaNode(colander.String(),
                                    default='',
                                    missing='')
    phone = colander.SchemaNode(colander.String(),
                                default='',
                                missing='')
    address = colander.SchemaNode(colander.String(),
                                  default='',
                                  missing='')
    memberof = ObjectIdList(missing=[], default=[])


class Users(colander.SequenceSchema):
    users = User()


class Policy(colander.MappingSchema):
    _id = colander.SchemaNode(colander.String())
    name = colander.SchemaNode(colander.String())
    type = colander.SchemaNode(colander.String())


class Policies(colander.SequenceSchema):
    policies = Policy()


class OrganisationalUnit(Node):
    policies = Policies()


class OrganisationalUnits(colander.SequenceSchema):
    organisationalunits = OrganisationalUnit()


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
    family = colander.SchemaNode(colander.String(),  # FIXME it's a choices
                                 default='',
                                 missing='')
    serial = colander.SchemaNode(colander.String(),
                                 default='',
                                 missing='')
    registry = colander.SchemaNode(colander.String(),
                                   default='',
                                   missing='')
    extra = colander.SchemaNode(colander.String(),
                                default='',
                                missing='')


class Computers(colander.SequenceSchema):
    computers = Computer()


class Storage(Node):
    memberof = ObjectIdList(missing=[], default=[])
    server = colander.SchemaNode(colander.String(),
                                 default='',
                                 missing='')
    port = colander.SchemaNode(colander.String(),  # FIXME it's a number
                               default='',
                               missing='')
    protocol = colander.SchemaNode(colander.String(),  # FIXME it's a choices
                                   default='',
                                   missing='')
    devicepath = colander.SchemaNode(colander.String(),
                                     default='',
                                     missing='')
    mount = colander.SchemaNode(colander.String(),
                                default='',
                                missing='')
    extraops = colander.SchemaNode(colander.String(),
                                   default='',
                                   missing='')


class Storages(colander.SequenceSchema):
    storages = Storage()


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
