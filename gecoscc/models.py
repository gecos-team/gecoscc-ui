from bson import ObjectId
from bson.objectid import InvalidId

import colander


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
            raise colander.Invalid(node, '{0} is not a ObjectId'.format(appstruct))
        return unicode(appstruct)

    def deserialize(self, node, cstruct):
        if cstruct is colander.null:
            if isinstance(node.missing, colander._drop):
                return colander.drop
            return colander.null
        try:
            return ObjectId(cstruct)
        except InvalidId:
            raise colander.Invalid(node, '{0} is not a valid id'.format(cstruct))
        except TypeError:
            raise colander.Invalid(node, '{0} is not a objectid string'.format(cstruct))

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


class Nodes(colander.SequenceSchema):
    nodes = Node()


class ObjectIdList(colander.SequenceSchema):
    item = colander.SchemaNode(ObjectIdField(),
                               default=[],
                               missing=[])


class Group(colander.MappingSchema):
    _id = colander.SchemaNode(ObjectIdField())
    name = colander.SchemaNode(colander.String())

    # Group objects
    memberof = colander.SchemaNode(ObjectIdField(),
                                   missing=colander.drop)

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
