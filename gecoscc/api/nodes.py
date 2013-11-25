import logging

from cornice import Service

from gecoscc.models import Nodes
from gecoscc.permissions import api_login_required


logger = logging.getLogger(__name__)


desc = """\
nodes resource allow to retrieve tree structure
"""

nodes_service = Service(name='nodes', path='/api/nodes/',
                        description='Logged user attributes')


def nodes_type_filter(request):
    type = request.GET.get('type')
    if type:
        return {
            'type': type,
        }
    return {}


def nodes_maxdepth_filter(request):
    maxdepth = int(request.GET.get('maxdepth'))
    path = request.GET.get('path', 'root')
    range_depth = '0,{0}'.format(maxdepth)
    return {
        'path': {
            '$regex': r'^{0}(,[^,]*){{{1}}}$'.format(path, range_depth),
        }
    }


def nodes_path_filter(request):
    path = request.GET.get('path')
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

    filters = []
    for (filter_name, filter_func) in node_filters.iteritems():
        if filter_name in request.GET:
            filter_dict = filter_func(request)
            if filter_dict:
                filters.append(filter_dict)

    logger.debug(str(filters))

    if filters:
        if len(filters) > 1:
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
