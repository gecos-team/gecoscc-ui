from cornice import Service

from gecoscc.models import Nodes


nodes_service = Service(name='nodes', path='/api/nodes/',
                          description='Logged user attributes')


@nodes_service.get()
def nodes_list(request):
    raw_nodes = request.db.nodes.find()

    schema = Nodes()
    nodes = schema.serialize(raw_nodes)

    return nodes
