
from cornice.resource import resource

from pyramid.threadlocal import get_current_request, get_current_registry

from gecoscc.api import ResourcePaginatedReadOnly
from gecoscc.i18n import is_default_language
from gecoscc.models import Policy, Policies
from gecoscc.permissions import api_login_required


def policies_targets_filter(params):
    target = params.get('target')
    return {
        'targets': target
    }


policies_filters = {
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

    @property
    def order_field(self):
        if is_default_language():
            return 'name'
        return 'name_%s' % get_current_request().locale_name

    def set_name_filter(self, query, key_name='name'):
        if not is_default_language():
            key_name = 'name_%s' % get_current_request().locale_name
        super(PoliciesResource, self).set_name_filter(query, key_name)

    def get_objects_filter(self):
        filters = super(PoliciesResource, self).get_objects_filter()

        permissions_filters = []

        local_filters = get_filters(policies_filters, self.request.GET)

        if local_filters:
            filters += local_filters
        if permissions_filters:
            filters += permissions_filters
        return filters
