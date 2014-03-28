from bson import ObjectId

from cornice.resource import resource
#from pyramid.httpexceptions import HTTPNotFound

from gecoscc.permissions import api_login_required

from gecoscc.models import Policy, Policies

#from gecoscc.policies import PoliciesManager, PolicyDoesNotExist

from gecoscc.api import ResourcePaginatedReadOnly


def policies_oids_filter(params):
    oids = params.get('oids')
    return {
        '$or': [{'_id': ObjectId(oid)} for oid in oids.split(',')]
    }


policies_filters = {
    'oids': policies_oids_filter,
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

    #mongo_filter = {}
    objtype = 'policies'
    collection_name = 'policies'

    #def collection_get(self):
        #page = int(self.request.GET.get('page', 0))
        #pagesize = int(self.request.GET.get('pagesize', self.default_pagesize))

        #policies_manager = PoliciesManager()

        #extraargs = {}
        #if pagesize > 0:
            #extraargs.update({
                #'skip': page * pagesize,
                #'limit': pagesize,
            #})

        #objects = policies_manager.get_policies()

        #if pagesize > 0:
            #pages = int(len(objects) / pagesize)
        #else:
            #pagesize = 1
        #objects = objects[page * pagesize:]
        #objects = objects[:pagesize]
        #parsed_objects = self.parse_collection(list(objects))
        #return {
            #'pagesize': pagesize,
            #'pages': pages,
            #'page': page,
            #self.collection_name: parsed_objects,
        #}

    #def get(self):
        #name = self.request.matchdict['name']

        #policies_manager = PoliciesManager()

        #try:
            #policy = policies_manager.get_policy(name)
        #except PolicyDoesNotExist:
            #raise HTTPNotFound()

        #return self.parse_item(policy)

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
