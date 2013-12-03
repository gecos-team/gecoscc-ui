import logging

from cornice import Service

from gecoscc.models import Nodes
from gecoscc.permissions import api_login_required, get_user_permissions


logger = logging.getLogger(__name__)


desc = """\
nodes resource allow to retrieve tree structure
"""

nodes_service = Service(name='nodes', path='/api/nodes/',
                        description='Logged user attributes')


def nodes_type_filter(params):
    type = params.get('type')
    if type:
        return {
            'type': type,
        }
    return {}


def nodes_maxdepth_filter(params):
    maxdepth = int(params.get('maxdepth'))
    path = params.get('path', 'root')
    range_depth = '0,{0}'.format(maxdepth)
    return {
        'path': {
            '$regex': r'^{0}(,[^,]*){{{1}}}$'.format(path, range_depth),
        }
    }


def nodes_path_filter(params):
    path = params.get('path')
    if path:
        return {
            'path': {
                '$regex': '^{0}'.format(path),
            }
        }
    return {}


node_filters = {
    'type': nodes_type_filter,
    'maxdepth': nodes_maxdepth_filter,
    'path': nodes_path_filter,
}


def get_filters(node_filters, params):
    filters = []
    for (filter_name, filter_func) in node_filters.iteritems():
        if filter_name in params:
            filter_dict = filter_func(params)
            if filter_dict:
                filters.append(filter_dict)
    return filters


@nodes_service.get(validators=(api_login_required,))
def nodes_list(request):
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

    local_filters = get_filters(node_filters, request.GET)

    permissions_filters = get_user_permissions(request)

    logger.debug(str(local_filters))
    logger.debug(str(permissions_filters))

    filters = local_filters + permissions_filters

    if local_filters:
        if len(local_filters) > 1:
            raw_nodes = request.db.nodes.find({
                '$and': filters,
            })
        else:
            raw_nodes = request.db.nodes.find(filters[0])
    else:
        raw_nodes = request.db.nodes.find()

    schema = Nodes()
    nodes = schema.serialize(raw_nodes)

    return nodes
