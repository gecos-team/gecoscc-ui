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
            return colander.null
        if not isinstance(appstruct, ObjectId):
            raise colander.Invalid(node, '{0} is not a ObjectId'.format(appstruct))
        return unicode(appstruct)

    def deserialize(self, node, cstruct):
        if cstruct is colander.null:
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
    lock = colander.SchemaNode(colander.Boolean())
    source = colander.SchemaNode(colander.String())
    name = colander.SchemaNode(colander.String())


class Nodes(colander.SequenceSchema):
    nodes = Node()


class Group(colander.MappingSchema):
    _id = colander.SchemaNode(ObjectIdField())
    name = colander.SchemaNode(colander.String())


class Groups(colander.SequenceSchema):
    groups = Group()


class User(Node):
    email = colander.SchemaNode(colander.String())
    groups = Groups()


class Policy(colander.MappingSchema):
    _id = colander.SchemaNode(colander.String())
    name = colander.SchemaNode(colander.String())
    type = colander.SchemaNode(colander.String())


class Policies(colander.SequenceSchema):
    policies = Policy()


class OrganisationalUnit(Node):
    pilicies = Policies()
