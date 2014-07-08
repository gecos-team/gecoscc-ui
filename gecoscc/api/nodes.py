import pymongo

from bson import ObjectId

from gecoscc.permissions import api_login_required

from cornice.resource import resource

from gecoscc.models import Nodes, Node
from gecoscc.api import ResourcePaginatedReadOnly


def nodes_type_filter(request):
    type = request.GET.get('type')
    if type:
        return {
            'type': type,
        }
    return {}


def nodes_path_filter(request):
    params = request.GET
    maxdepth = int(params.get('maxdepth'))
    path = request.GET.get('path', 'root')
    range_depth = '0,{0}'.format(maxdepth)
    ou_managed_ids = request.user.get('ou_managed', [])
    if not request.user.get('is_superuser') or ou_managed_ids:
        ou_managed_ids = [ObjectId(ou_managed_id) for ou_managed_id in ou_managed_ids]
        if path == 'root':
            return {
                '_id': {'$in': ou_managed_ids}
            }
    return {
        'path': {
            '$regex': r'^{0}(,[^,]*){{{1}}}$'.format(path, range_depth),
        }
    }


def nodes_oids_filter(request):
    oids = request.GET.get('oids')
    return {
        '$or': [{'_id': ObjectId(oid)} for oid in oids.split(',')]
    }


node_filters = {
    'type': nodes_type_filter,
    'path': nodes_path_filter,
    'oids': nodes_oids_filter,
}


def get_filters(node_filters, request):
    filters = []
    params = request.GET
    for (filter_name, filter_func) in node_filters.iteritems():
        if filter_name in params:
            filter_dict = filter_func(request)
            if filter_dict:
                filters.append(filter_dict)
    return filters


@resource(collection_path='/api/nodes/',
          path='/api/nodes/{oid}/',
          description='Nodes resource',
          validators=(api_login_required,))
class NodesResource(ResourcePaginatedReadOnly):
    """ Returns the nodes tree structure

    GET filters:
        type (str): One of 'ou', 'user', 'printer', 'storage'
        path (str): The base path for the query (comma separated items)
        maxdepth (int): The max children levels to retrieve

    Returns [{
            name: "user_20",
            lock: "false",
            source: "gecos",
            path: "root,ou_0,ou_1,ou_2,user_20",
            _id: "528f2aa5e22ef080a9ae16eb",
            type: "user",
        },
        ...
    ]
    """

    schema_collection = Nodes
    schema_detail = Node

    mongo_filter = {
    }
    collection_name = 'nodes'
    objtype = 'nodes'
    order_field = [('node_order', pymongo.ASCENDING),
                   ('_id', pymongo.ASCENDING)]

    def get_objects_filter(self):
        # TODO
        # Implement permissions filter
        # permissions_filters = get_user_permissions(self.request)
        filters = super(NodesResource, self).get_objects_filter()

        permissions_filters = []

        local_filters = get_filters(node_filters, self.request)

        if local_filters:
            filters += local_filters
        if permissions_filters:
            filters += permissions_filters

        return filters

    def get_object_filter(self):
        # TODO
        # Implement permissions filter
        # permissions_filters = get_user_permissions(self.request)
        return {}
