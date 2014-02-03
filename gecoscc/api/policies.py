
from cornice.resource import resource
from pyramid.httpexceptions import HTTPNotFound

from gecoscc.permissions import api_login_required

from gecoscc.models import Policy, Policies

from gecoscc.policies import PoliciesManager, PolicyDoesNotExist

from . import ResourcePaginatedReadOnly


@resource(collection_path='/api/policies/',
          path='/api/policies/{name}/',
          description='Policies resource',
          validators=(api_login_required,))
class PoliciesResource(ResourcePaginatedReadOnly):

    schema_collection = Policies
    schema_detail = Policy

    objtype = 'policy'
    collection_name = 'policies'

    def collection_get(self):
        page = int(self.request.GET.get('page', 0))
        pagesize = int(self.request.GET.get('pagesize', self.default_pagesize))

        policies_manager = PoliciesManager()

        extraargs = {}
        if pagesize > 0:
            extraargs.update({
                'skip': page * pagesize,
                'limit': pagesize,
            })

        objects = policies_manager.get_policies()

        if pagesize > 0:
            pages = int(len(objects) / pagesize)
        else:
            pagesize = 1
        objects = objects[page * pagesize:]
        objects = objects[:pagesize]
        parsed_objects = self.parse_collection(list(objects))
        return {
            'pagesize': pagesize,
            'pages': pages,
            'page': page,
            self.collection_name: parsed_objects,
        }

    def get(self):
        name = self.request.matchdict['name']

        policies_manager = PoliciesManager()

        try:
            policy = policies_manager.get_policy(name)
        except PolicyDoesNotExist:
            raise HTTPNotFound()

        return self.parse_item(policy)
