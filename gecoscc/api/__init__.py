from bson import ObjectId
from copy import deepcopy

from cornice.schemas import CorniceSchema

from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest

SAFE_METHODS = ('GET', 'OPTIONS', 'HEAD',)
UNSAFE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE', )
SCHEMA_METHODS = ('POST', 'PUT', )


class ResourcePaginatedReadOnly(object):
    # TODO
    # Implement permissions filter

    schema_collection = None
    schema_detail = None
    mongo_filter = {
        'type': 'anytype',
    }
    collection_name = 'nodes'
    key = '_id'

    def __init__(self, request):
        self.request = request
        self.default_pagesize = request.registry.settings.get(
            'default_pagesize', 30)
        self.collection = self.get_collection()

    def parse_item(self, item):
        serialized_item = self.schema_detail().deserialize(item)
        return self.schema_detail().serialize(serialized_item)

    def parse_collection(self, collection):
        serialized_data = self.schema_collection().deserialize(collection)
        return self.schema_collection().serialize(serialized_data)

    def get_objects_filter(self):
        return {}

    def get_object_filter(self):
        return {}

    def get_oid_filter(self, oid):
        return {self.key: ObjectId(oid)}

    def get_collection(self, collection=None):
        if collection is None:
            collection = self.collection_name
        return self.request.db[collection]

    def collection_get(self):
        page = int(self.request.GET.get('page', 0))
        pagesize = int(self.request.GET.get('pagesize', self.default_pagesize))

        extraargs = {}
        if pagesize > 0:
            extraargs.update({
                'skip': page*pagesize,
                'limit': pagesize,
            })

        users_count = self.collection.find(
            self.mongo_filter,
            {'type': 1}
        ).count()

        collection_filter = self.get_objects_filter()

        collection_filter.update(self.mongo_filter)

        objects = self.collection.find(collection_filter, **extraargs)
        if pagesize > 0:
            pages = int(users_count / pagesize)
        else:
            pagesize = 1
        return {
            'pagesize': pagesize,
            'pages': pages,
            'page': page,
            self.collection_name: self.parse_collection(list(objects)),
        }

    def get(self):
        oid = self.request.matchdict['oid']
        collection_filter = self.get_oid_filter(oid)
        collection_filter.update(self.get_object_filter())
        collection_filter.update(self.mongo_filter)
        user = self.collection.find_one(collection_filter)
        if not user:
            raise HTTPNotFound()

        return self.parse_item(user)


class ResourcePaginated(ResourcePaginatedReadOnly):

    def __init__(self, request):
        super(ResourcePaginated, self).__init__(request)
        if request.method in SCHEMA_METHODS:
            self.schema = CorniceSchema(self.schema_detail)
            # Implement write permissions

    def integrity_validation(self, obj, real_obj=None):
        return True

    def pre_save(self, obj, old_obj=None):
        return obj

    def post_save(self, obj, old_obj=None):
        return obj

    def pre_delete(self, obj, old_obj=None):
        return obj

    def post_delete(self, obj, old_obj=None):
        return obj

    def collection_post(self):
        obj = self.request.validated

        if not self.integrity_validation(obj):
            if len(self.request.errors) < 1:
                self.request.errors.add('body', 'object', 'Integrity error')
            return

        # Remove '_id' for security reasons
        del obj[self.key]

        obj = self.pre_save(self, obj)

        obj_id = self.collection.insert(obj)

        obj = self.post_save(self, obj)

        return {self.key: str(obj_id)}

    def put(self):
        obj = self.request.validated
        oid = self.request.matchdict['oid']

        if oid != str(obj[self.key]):
            raise HTTPBadRequest('The object id is not the same that the id in'
                                 ' the url')

        obj_filter = self.get_oid_filter(oid)
        obj_filter.update(self.mongo_filter)

        real_obj = self.collection.find_one(obj_filter)
        if not real_obj:
            raise HTTPNotFound()
        old_obj = deepcopy(real_obj)
        if not self.integrity_validation(obj, real_obj=real_obj):
            if len(self.request.errors) < 1:
                self.request.errors.add('body', 'object', 'Integrity error')
            return

        obj = self.pre_save(obj, old_obj=old_obj)

        real_obj.update(obj)
        self.collection.update(obj_filter, real_obj, new=True)

        obj = self.post_save(obj, old_obj=old_obj)

        return self.parse_item(obj)

    def delete(self):

        obj_id = self.request.matchdict['oid']

        filter = self.get_oid_filter(obj_id)
        filter.update(self.mongo_filter)

        obj = self.collection.find_one(filter)
        if not obj:
            raise HTTPNotFound()
        old_obj = deepcopy(obj)

        if not self.integrity_validation(obj):
            if len(self.request.errors) < 1:
                self.request.errors.add('body', 'object', 'Integrity error')
            return

        obj = self.pre_save(obj)
        obj = self.pre_delete(obj)

        status = self.collection.remove(filter)

        if status['ok']:
            obj = self.post_save(obj, old_obj)
            obj = self.post_delete(obj)
            return {
                'status': 'The object was deleted successfully',
                'ok': 1
            }
        else:
            self.request.errors.add('operation', 'db status', status)
            return


class TreeResourcePaginated(ResourcePaginated):

    def integrity_validation(self, obj, real_obj=None):
        """ Test that the object path already exist """

        if real_obj is not None and obj['path'] == real_obj['path']:
            # This path was already verified before
            return True

        parents = obj['path'].split(',')

        parent_id = parents[-1]

        if parent_id == 'root':
            return True

        parent = self.collection.find_one({self.key: ObjectId(parent_id)})
        if not parent:
            self.request.errors.add('operation', 'path', "parent"
                                    " doesn't exist {0}".format(parent_id))
            return False

        candidate_path_parent = ','.join(parents[:-1])

        if parent['path'] != candidate_path_parent:
            self.request.errors.add(
                'operation', 'path', "the parent object "
                "{0} has a different path".format(parent_id))
            return False

        return True
