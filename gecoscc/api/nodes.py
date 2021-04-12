#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Antonio Perez-Aranda <ant30tx@gmail.com>
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import pymongo

from cornice.resource import resource

from gecoscc.api import ResourcePaginatedReadOnly
from gecoscc.models import Nodes, Node
from gecoscc.permissions import api_login_required


def nodes_type_filter(request):
    type_filter = request.GET.get('type')
    if type_filter:
        if ',' in type_filter:
            types = type_filter.split(',')
            return {
                'type': { '$in': types },
            }

        else:
            return {
                'type': type_filter,
            }
    return {}


node_filters = {
    'type': nodes_type_filter,
}


def get_filters(node_filters, request):
    filters = []
    params = request.GET
    for (filter_name, filter_func) in list(node_filters.items()):
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
        search_by: One of 'ip', 'nodename' or 'username'
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
    order_field = [('node_order', pymongo.DESCENDING),
                   ('name', pymongo.ASCENDING)]

    def get_objects_filter(self):
        filters = super(NodesResource, self).get_objects_filter()

        permissions_filters = []

        local_filters = get_filters(node_filters, self.request)

        if local_filters:
            filters += local_filters
        if permissions_filters:
            filters += permissions_filters
        return filters
