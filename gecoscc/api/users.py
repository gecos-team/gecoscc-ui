from bson import ObjectId

from gecoscc.models import User, Users

from cornice.resource import resource


@resource(collection_path='/api/users/',
          path='/api/users/{oid}/')
class UserResource(object):

    def __init__(self, request):
        self.request = request
        self.collection_schema = Users()
        self.detail_schema = User()
        self.default_pagesize = request.registry.settings.get('default_pagesize', 30)

    def parse_item(self, item):
        serialized_item = self.detail_schema.deserialize(item)
        return self.detail_schema.serialize(serialized_item)

    def parse_collection(self, collection):
        serialized_data = self.collection_schema.deserialize(collection)
        return self.collection_schema.serialize(serialized_data)

    def collection_get(self):
        page = int(self.request.GET.get('page', 0))
        pagesize = int(self.request.get('pagesize', self.default_pagesize))

        extraargs = {}
        if pagesize > 0:
            extraargs.update({
                'skip': page*pagesize,
                'limit': pagesize,
            })

        users_count = self.request.db.nodes.find(
            {'type': 'user'},
            {'type': 1}
        ).count()
        users = self.request.db.nodes.find({
            'type': 'user',
        }, **extraargs)
        pages = int(users_count / pagesize)
        return self.parse_collection({
            'pagesize': pagesize,
            'pages': pages,
            'page': page,
            'users': list(users),
        })

    def get(self):
        oid = self.request.matchdict['oid']
        user = self.request.db.nodes.find_one({
            '_id': ObjectId(oid),
            'type': 'user',
        })
        return self.parse_item(user)
