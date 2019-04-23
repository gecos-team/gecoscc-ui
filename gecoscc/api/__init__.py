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

import cgi
import os

from bson import ObjectId
from copy import deepcopy

from cornice.schemas import CorniceSchema
from pymongo.errors import DuplicateKeyError
from pyramid.httpexceptions import HTTPNotFound, HTTPBadRequest, HTTPForbidden
from webob.multidict import MultiDict

from gecoscc.models import Node
from gecoscc.permissions import (can_access_to_this_path, nodes_path_filter,
                                 is_gecos_master_or_403,
                                 master_policy_no_updated_or_403)
from gecoscc.socks import invalidate_change, invalidate_delete
from gecoscc.tasks import (object_created, object_changed, object_deleted, 
                           object_moved, object_refresh_policies)
from gecoscc.utils import (get_computer_of_user, get_filter_nodes_parents_ou,
                           oids_filter, check_unique_node_name_by_type_at_domain,
                           visibility_object_related, visibility_group,
                           RESOURCES_EMITTERS_TYPES, get_object_related_list)

import gettext
import logging
logger = logging.getLogger(__name__)

SAFE_METHODS = ('GET', 'OPTIONS', 'HEAD',)
UNSAFE_METHODS = ('POST', 'PUT', 'PATCH', 'DELETE', )
SCHEMA_METHODS = ('POST', 'PUT', )


class BaseAPI(object):

    order_field = '_id'

    def __init__(self, request):
        self.request = request
        self.collection = self.get_collection()
        localedir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'locale')
        gettext.bindtextdomain('gecoscc', localedir)
        gettext.textdomain('gecoscc')
        self._ = gettext.gettext                                

    def parse_item(self, item):
        return self.schema_detail().serialize(item)

    def parse_collection(self, collection):
        return self.schema_collection().serialize(collection)

    def get_collection(self, collection=None):
        if collection is None:
            collection = self.collection_name
        return self.request.db[collection]

    def set_variables(self, method):
        request = self.request
        fs = cgi.FieldStorage(fp=request.body_file,
                              environ=request.environ.copy(),
                              keep_blank_values=True)
        setattr(self.request, method, MultiDict.from_fieldstorage(fs))


class ResourcePaginatedReadOnly(BaseAPI):

    schema_collection = None
    schema_detail = None
    mongo_filter = {
        'type': 'anytype',
    }
    collection_name = 'nodes'
    objtype = None
    key = '_id'

    def __init__(self, request):
        super(ResourcePaginatedReadOnly, self).__init__(request)
        self.default_pagesize = request.registry.settings.get(
            'default_pagesize', 30)
        if self.objtype is None:
            raise self.BadResourceDefinition('objtype is not defined')

    class BadResourceDefinition(Exception):
        pass

    def set_name_filter(self, query, key_name='name'):
        if 'name' in self.request.GET:
            query.append({
                key_name: self.request.GET.get('name')
            })

        if 'iname' in self.request.GET:
            query.append({
                key_name: {
                    '$regex': u'.*{0}.*'.format(self.request.GET.get('iname')),
                    '$options': '-i'
                }
            })

    def set_username_filter(self, query):
        if 'iname' in self.request.GET:
            # Look for users with that username (or similar)
            users = self.request.db.nodes.find({"type": "user", "name": {
                    '$regex': u'.*{0}.*'.format(self.request.GET.get('iname')),
                    '$options': '-i'
                }})
            
            # Merge the list of computers
            computer_ids = []
            for user in users:
                computer_ids = computer_ids + user['computers']

            # Append the list of computers to the query
            query.append({
                "_id": {
                    "$in": computer_ids
                }
            })    
            
    def get_objects_filter(self):
        query = []
        if not self.request.method == 'GET':
            return []

        if 'search_by' in self.request.GET:
            search_by = self.request.GET.get('search_by')
            if search_by == 'ip':
                # Search by IPv4 address
                self.set_name_filter(query, 'ipaddress')

            elif search_by == 'username':
                # Search by username
                self.set_username_filter(query)

            else:
                # Default: search by node name
                self.set_name_filter(query)
            
        else:
            # Default: search by node name
            self.set_name_filter(query)

        if 'oids' in self.request.GET:
            oid_filters = oids_filter(self.request)
            if oid_filters:
                query.append(oid_filters)

        if issubclass(self.schema_detail, Node):
            path_filter = nodes_path_filter(self.request, ['ou_managed','ou_readonly'])
            if path_filter:
                query.append(path_filter)

        return query

    def get_object_filter(self):
        return {}

    def get_distinct_filter(self, objects):
        return objects

    def get_oid_filter(self, oid):
        return {self.key: ObjectId(oid)}

    def collection_get(self):
        page = int(self.request.GET.get('page', 1))
        pagesize = int(self.request.GET.get('pagesize', self.default_pagesize))
        if pagesize <= 0 or page <= 0:
            raise HTTPBadRequest()
        extraargs = {
            'skip': (page - 1) * pagesize,
            'limit': pagesize,
        }

        objects_filter = self.get_objects_filter()
        if self.mongo_filter:
            objects_filter.append(self.mongo_filter)

        if objects_filter:
            mongo_query = {
                '$and': objects_filter,
            }
        else:
            mongo_query = {}

        nodes_count = self.collection.find(
            mongo_query,
            {'type': 1}
        ).count()

        objects = self.collection.find(mongo_query, **extraargs).sort(self.order_field)
        objects = self.get_distinct_filter(objects)
        pages = int(nodes_count / pagesize)
        if nodes_count % pagesize > 0:
            pages += 1
        parsed_objects = self.parse_collection(list(objects))
        return {
            'pagesize': pagesize,
            'pages': pages,
            'page': page,
            self.collection_name: parsed_objects,
            'total': nodes_count,
        }

    def get(self):
        oid = self.request.matchdict['oid']
        if issubclass(self.schema_detail, Node):
            try:
                can_access_to_this_path(self.request, self.collection, oid, ou_type='ou_readonly')
            except HTTPForbidden:
                can_access_to_this_path(self.request, self.collection, oid)
        collection_filter = self.get_oid_filter(oid)
        collection_filter.update(self.get_object_filter())
        collection_filter.update(self.mongo_filter)
        node = self.collection.find_one(collection_filter)
        if not node:
            raise HTTPNotFound()
        node = self.parse_item(node)

        if node.get('type', None) in RESOURCES_EMITTERS_TYPES:
            node['is_assigned'] = self.is_assigned(node)
            return node
        return node
        
    def is_assigned(self, related_object):
        node_with_related_object = get_object_related_list(self.request.db, related_object)
        return bool(node_with_related_object.count())


class ResourcePaginated(ResourcePaginatedReadOnly):

    def __init__(self, request):
        super(ResourcePaginated, self).__init__(request)
        if request.method == 'POST':
            schema = self.schema_detail()
            del schema['_id']
            self.schema = CorniceSchema(schema)

        elif request.method == 'PUT':
            self.schema = CorniceSchema(self.schema_detail)
            # Implement write permissions

    def integrity_validation(self, obj, real_obj=None):
        return True

    def pre_save(self, obj, old_obj=None):
        if old_obj and 'name' in old_obj:
            obj['name'] = old_obj['name']

        # Check he policies "object_related_list" attribute
        if 'policies' in obj:
            policies = obj['policies']
            for policy in policies:
                # Get the policy
                policyobj = self.request.db.policies.find_one({"_id": ObjectId(str(policy))})
                if policyobj is None:
                    logger.warning("Unknown policy: %s" % (str(policy)))
                else:
                    # Get the related object collection
                    ro_collection = None
                    if policyobj['slug'] == 'printer_can_view':
                        ro_collection = self.request.db.nodes
                    elif policyobj['slug'] == 'repository_can_view':
                        ro_collection = None
                    elif policyobj['slug'] == 'storage_can_view':
                        ro_collection = self.request.db.nodes
                    elif policyobj['slug'] == 'local_users_res':
                        ro_collection = None
                    else:
                        logger.warning("Unrecognized slug: %s" % (str(policyobj['slug'])))

                    # Check the related objects
                    if ro_collection is not None:
                        ro_list = policies[str(policy)]['object_related_list']
                        for ro_id in ro_list:
                            ro_obj = ro_collection.find_one({"_id": ObjectId(str(ro_id))})
                            if ro_obj is None:
                                logger.error("Can't find related object: %s:%s" % (str(policyobj['slug']), str(ro_id)))
                                self.request.errors.add('body', 'object', "Can't find related object: %s:%s" % (str(policyobj['slug']), str(ro_id)))
                                return None

        else:
            logger.debug("No policies in this object")

        return obj

    def post_save(self, obj, old_obj=None):
        return obj

    def pre_delete(self, obj, old_obj=None):
        return obj

    def post_delete(self, obj, old_obj=None):
        return obj

    def collection_post(self):
        obj = self.request.validated

        if issubclass(self.schema_detail, Node):
            can_access_to_this_path(self.request, self.collection, obj)
            is_gecos_master_or_403(self.request, self.collection, obj, self.schema_detail)
            master_policy_no_updated_or_403(self.request, self.collection, obj)

        if not self.integrity_validation(obj):
            if len(self.request.errors) < 1:
                self.request.errors.add('body', 'object', 'Integrity error')
            return

        # Remove '_id' for security reasons
        if self.key in obj:
            del obj[self.key]

        obj = self.pre_save(obj)
        if obj is None:
            return

        try:
            obj_id = self.collection.insert(obj)
        except DuplicateKeyError, e:
            raise HTTPBadRequest('The Object already exists: '
                                 '{0}'.format(e.message))

        obj = self.post_save(obj)

        obj.update({self.key: obj_id})
        self.notify_created(obj)
        return self.parse_item(obj)

    def notify_created(self, obj):
        object_created.delay(self.request.user, self.objtype, obj)

    def notify_changed(self, obj, old_obj):
        if obj['path'] != old_obj['path']:
            object_moved.delay(self.request.user, self.objtype, obj, old_obj)
        else:
            object_changed.delay(self.request.user, self.objtype, obj, old_obj)
            invalidate_change(self.request, obj)

    def notify_deleted(self, obj):
        object_deleted.delay(self.request.user, self.objtype, obj)
        invalidate_delete(self.request, obj)

    def notify_refresh_policies(self, obj):
        object_refresh_policies.delay(self.request.user, self.objtype, obj)
        invalidate_change(self.request, obj)



    def put(self):
        obj = self.request.validated
        oid = self.request.matchdict['oid']

        if oid != str(obj[self.key]):
            raise HTTPBadRequest('The object id is not the same that the id in'
                                 ' the url')

        if issubclass(self.schema_detail, Node):
            can_access_to_this_path(self.request, self.collection, oid)
            is_gecos_master_or_403(self.request, self.collection, obj, self.schema_detail)
            master_policy_no_updated_or_403(self.request, self.collection, obj)

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
        if obj is None:
            return

        inheritance_backup = None
        if 'inheritance' in obj:
            # Do not save the inheritance field
            inheritance_backup = obj['inheritance']
            del obj['inheritance']
            
        real_obj.update(obj)
        
        try:
            self.collection.update(obj_filter, real_obj, new=True)
        except DuplicateKeyError, e:
            raise HTTPBadRequest('Duplicated object {0}'.format(
                e.message))

        obj = self.post_save(obj, old_obj=old_obj)
        self.notify_changed(obj, old_obj)
        obj = self.parse_item(obj)
        
        if inheritance_backup is not None:
            obj['inheritance'] = inheritance_backup
        
        return obj



    def refresh_policies(self):
        obj = self.request.validated
        oid = self.request.matchdict['oid']

        if oid != str(obj[self.key]):
            raise HTTPBadRequest('The object id is not the same that the id in'
                                 ' the url')

        if issubclass(self.schema_detail, Node):
            can_access_to_this_path(self.request, self.collection, oid)
            is_gecos_master_or_403(self.request, self.collection, obj, self.schema_detail)
            master_policy_no_updated_or_403(self.request, self.collection, obj)

        obj_filter = self.get_oid_filter(oid)
        obj_filter.update(self.mongo_filter)

        real_obj = self.collection.find_one(obj_filter)
        if not real_obj:
            raise HTTPNotFound()
            
        self.notify_refresh_policies(real_obj)
        
        obj = self.parse_item(real_obj)
        
        return obj


    def delete(self):

        oid = self.request.matchdict['oid']

        if issubclass(self.schema_detail, Node):
            obj = self.collection.find_one({'_id': ObjectId(oid)})
            can_access_to_this_path(self.request, self.collection, oid)
            is_gecos_master_or_403(self.request, self.collection, obj, self.schema_detail)
            master_policy_no_updated_or_403(self.request, self.collection, obj)

        filters = self.get_oid_filter(oid)
        filters.update(self.mongo_filter)

        obj = self.collection.find_one(filters)
        if not obj:
            raise HTTPNotFound()
        old_obj = deepcopy(obj)

        obj = self.pre_save(obj)
        if obj is None:
            return
        obj = self.pre_delete(obj)

        status = self.collection.remove(filters)

        if status['ok']:
            obj = self.post_save(obj, old_obj)
            obj = self.post_delete(obj)

            self.notify_deleted(obj)
            return {
                'status': 'The object was deleted successfully',
                'ok': 1
            }
        else:
            self.request.errors.add(unicode(obj[self.key]), 'db status',
                                    status)
            return


class TreeResourcePaginated(ResourcePaginated):

    def check_unique_node_name_by_type_at_domain(self, obj):
        unique = check_unique_node_name_by_type_at_domain(self.request.db.nodes, obj)
        if not unique:
            self.request.errors.add('body', 'name',
                                    "Name must be unique in domain.")
        return unique

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
            self.request.errors.add(unicode(obj[self.key]), 'path', "parent"
                                    " doesn't exist {0}".format(parent_id))
            return False

        candidate_path_parent = ','.join(parents[:-1])

        if parent['path'] != candidate_path_parent:
            self.request.errors.add(
                unicode(obj[self.key]), 'path', "the parent object "
                "{0} has a different path".format(parent_id))
            return False

        return True

# TODO: Only have to extends this class the ComputerResource and UserResource
# Now there are another class that extends it. I don't make it, because this
# could break another things


class TreeLeafResourcePaginated(TreeResourcePaginated):

    def check_memberof_integrity(self, obj):
        """ Check if memberof ids already exists or if the group is out of scope"""
        if 'memberof' not in obj:
            return True
        obj_validated = visibility_group(self.request.db, obj)
        if obj != obj_validated:
            self.request.errors.add(unicode(obj[self.key]), 'memberof',
                                    "There is a group out of scope.")
            return False
        for group_id in obj['memberof']:
            group = self.request.db.nodes.find_one({'_id': group_id})
            if not group:
                self.request.errors.add(
                    unicode(obj[self.key]), 'memberof',
                    "The group {0} doesn't exist".format(unicode(group_id)))
                return False
        return True

    def check_policies_integrity(self, obj, is_moved=False):
        """
        Check if the policie is out of scope
        """
        obj_original = deepcopy(obj)
        visibility_object_related(self.request.db, obj)
        if not is_moved:
            if obj != obj_original:
                self.request.errors.add(unicode(obj[self.key]), 'policies',
                                        "The related object is out of scope")
                return False
        return True

    def integrity_validation(self, obj, real_obj=None):
        result = super(TreeLeafResourcePaginated, self).integrity_validation(
            obj, real_obj)
        result = result and self.check_memberof_integrity(obj)
        result = result and self.check_unique_node_name_by_type_at_domain(obj)
        if real_obj is not None and real_obj['path'] == obj['path']:
            result = result and self.check_policies_integrity(obj)
        else:
            result = result and self.check_policies_integrity(obj, is_moved=True)
        return result

    def computers_to_group(self, obj):
        if obj['type'] == 'computer':
            return [obj]
        elif obj['type'] == 'user':
            return get_computer_of_user(self.collection, obj)
        raise ValueError("The object type should be computer or user")

    def post_save(self, obj, old_obj=None):
        if self.request.method == 'DELETE':
            newmemberof = []
        else:
            newmemberof = obj.get('memberof', [])
        if old_obj is not None:
            oldmemberof = old_obj.get('memberof', [])
        else:
            oldmemberof = []

        adds = [n for n in newmemberof if n not in oldmemberof]
        removes = [n for n in oldmemberof if n not in newmemberof]

        for group_id in removes:
            group = self.request.db.nodes.find_one({'_id': group_id})
            self.request.db.nodes.update({
                '_id': group_id
            }, {
                '$pull': {
                    'members': obj['_id']
                }
            }, multi=False)
            group_without_policies = self.request.db.nodes.find_one({'_id': group_id})
            group_without_policies['policies'] = {}
            computers = self.computers_to_group(obj)
            object_changed.delay(self.request.user, 'group', group_without_policies, group, 'changed', computers)

        for group_id in adds:

            # Add newmember to new group
            self.request.db.nodes.update({
                '_id': group_id
            }, {
                '$push': {
                    'members': obj['_id']
                }
            }, multi=False)
            group = self.request.db.nodes.find_one({'_id': group_id})
            computers = self.computers_to_group(obj)
            object_changed.delay(self.request.user, 'group', group, {}, 'changed', computers)

        return super(TreeLeafResourcePaginated, self).post_save(obj, old_obj)


class PassiveResourcePaginated(TreeLeafResourcePaginated):

    def get_objects_filter(self):
        filters = super(PassiveResourcePaginated, self).get_objects_filter()
        ou_id = self.request.GET.get('ou_id', None)
        item_id = self.request.GET.get('item_id', None)
        if ou_id and item_id:
            filters.append({'path': get_filter_nodes_parents_ou(self.request.db,
                                                                ou_id, item_id)})
        return filters

    def check_obj_is_related(self, obj):
        '''
        Check if the emitter object is related with any object
        '''
        if obj.get('_id'):
            if obj['type'] == 'printer':
                slug = 'printer_can_view'
            elif obj['type'] == 'repository':
                slug = 'repository_can_view'
            elif obj['type'] == 'storage':
                slug = 'storage_can_view'
            elif obj['type'] == 'group':
                members_group = obj['members']
                if not members_group:
                    return True
                return False

            policy_id = self.request.db.policies.find_one({'slug': slug}).get('_id')
            nodes_related_with_obj = self.request.db.nodes.find({"policies.%s.object_related_list"
                                                                % unicode(policy_id): {'$in': [unicode(obj['_id'])]}})

            if nodes_related_with_obj.count() == 0:
                return True

            return False
        return True

    def integrity_validation(self, obj, real_obj=None):
        result = super(PassiveResourcePaginated, self).integrity_validation(
            obj, real_obj)
        result = result and (self.request.user.get('is_superuser', False) or self.check_obj_is_related(obj))

        return result
