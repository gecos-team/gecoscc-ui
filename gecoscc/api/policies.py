from bson import ObjectId

from cornice.resource import resource

from gecoscc.api import ResourcePaginatedReadOnly
from gecoscc.models import Policy, Policies
from gecoscc.permissions import api_login_required
from gecoscc.utils import POLICY_EMITTER_SUBFIX, get_filter_nodes_parents_ou


def policies_oids_filter(params):
    oids = params.get('oids')
    return {
        '$or': [{'_id': ObjectId(oid)} for oid in oids.split(',')]
    }


def policies_targets_filter(params):
    target = params.get('target')
    return {
        'targets': target
    }


policies_filters = {
    'oids': policies_oids_filter,
    'target': policies_targets_filter,
}


def get_filters(policies_filters, params):
    filters = []
    for (filter_name, filter_func) in policies_filters.iteritems():
        if filter_name in params:
            filter_dict = filter_func(params)
            if filter_dict:
                filters.append(filter_dict)
    return filters


@resource(collection_path='/api/policies/',
          path='/api/policies/{oid}/',
          description='Policies resource',
          validators=(api_login_required,))
class PoliciesResource(ResourcePaginatedReadOnly):

    schema_collection = Policies
    schema_detail = Policy

    mongo_filter = {}
    objtype = 'policy'
    collection_name = 'policies'
    order_field = 'name'

    def parse_collection(self, objects):
        for obj in objects:
            is_emitter_policy = obj.get('is_emitter_policy', False)
            if is_emitter_policy:
                self.parse_emitter_policy(obj)
        return super(PoliciesResource, self).parse_collection(objects)

    def parse_emitter_policy(self, obj):
        ou_id = self.request.GET.get('ou_id', None)
        item_id = self.request.GET.get('item_id', None)
        if ou_id and item_id:
            node_type = obj['slug'].replace(POLICY_EMITTER_SUBFIX, '')
            nodes = self.request.db.nodes.find({'type': node_type,
                                                'path': get_filter_nodes_parents_ou(self.request.db, ou_id, item_id)})
            object_related_items = obj['schema']['properties']['object_related_list']['items']
            object_related_items['enum'] = [{"title": node["name"],
                                             "value": unicode(node["_id"])} for node in nodes]
        return obj

    def parse_item(self, obj):
        is_emitter_policy = obj.get('is_emitter_policy', False)
        if is_emitter_policy:
            obj = self.parse_emitter_policy(obj)
        return super(PoliciesResource, self).parse_item(obj)

    def get_objects_filter(self):
        # TODO
        # Implement permissions filter
        # permissions_filters = get_user_permissions(self.request)
        filters = super(PoliciesResource, self).get_objects_filter()

        permissions_filters = []

        local_filters = get_filters(policies_filters, self.request.GET)

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
