#
# Authors:
#   Pablo Iglesias <pabloig90@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from bson import ObjectId
from cornice.resource import resource
from chef import Node as ChefNode

from gecoscc.api.computers import ComputerResource
from gecoscc.permissions import api_login_required
from gecoscc.utils import (get_chef_api, recalc_node_policies,
                           priority_object)

from pyramid.response import Response


@resource(collection_path='/api/computers_policy/',
          path='/api/computers_policy/{oid}/',
          description='Computers_policy resource',
          validators=(api_login_required,))
class ComputerPolicies(ComputerResource):

    def get(self):
        result = super(ComputerResource, self).get()
        api = get_chef_api(self.request.registry.settings, self.request.user)
        computer_node = ChefNode(result['node_chef_id'], api)
        db = self.get_collection().database
        result.update({'details_policy': self.get_policies_applied(computer_node, db)})
        return result

    def put(self):
        if self.request.user.get('is_superuser', False):
            oid = self.request.matchdict['oid']
            obj_filter = self.get_oid_filter(oid)
            obj_filter.update(self.mongo_filter)
            real_obj = self.collection.find_one(obj_filter)
            api = get_chef_api(self.request.registry.settings, self.request.user)
            db = self.get_collection().database
            cookbook_name = self.request.registry.settings['chef.cookbook_name']
            recalc_node_policies(db.nodes, db.jobs, real_obj, self.request.user, cookbook_name, api=api)

        return Response('Not allowed.')

    def get_policies_and_objects(self, type_policies, db):
        '''
        Get the policies and the objects that applied this policies from node
        '''
        policies = []
        objects = []

        for type_policy in type_policies.keys():
                for policy_slug in type_policies.get(type_policy).keys():
                    policy_updated_by = type_policies.get(type_policy).get(policy_slug).get('updated_by')
                    if not policy_updated_by:
                        continue
                    if policy_slug in ('printers_res', 'user_shared_folder_res', 'software_sources_res'):
                        policy_slug = self.emitters_policy_slug(policy_slug)
                    policies.append(policy_slug)
                    for type_update_by in policy_updated_by.keys():
                        if type_update_by in ('ou', 'group', 'users'):
                            for update_by in policy_updated_by.get(type_update_by):
                                objects.append(ObjectId(update_by))
                        else:
                            objects.append(ObjectId(policy_updated_by.get(type_update_by)))

        policies_data = db.policies.find({'slug': {'$in': policies}}, {'slug': 1, '_id': 1, 'is_mergeable': 1, 'path': 1})
        objects_data = db.nodes.find({'_id': {'$in': objects}}, {'name': 1, '_id': 1, 'type': 1})
        policies_data = self.cursor_to_list(policies_data)
        objects_data = self.cursor_to_list(objects_data)

        return (policies_data, objects_data)

    def get_policies_applied(self, computer_node, db):
        '''
        Get the policies applied to the computer and the objects who applied this policies
        '''
        computer_policies = {}
        type_policies = computer_node.attributes.get('gecos_ws_mgmt')
        policies, objects = self.get_policies_and_objects(type_policies, db)

        for type_policy in type_policies.keys():
            for policy_slug in type_policies.get(type_policy).keys():
                policy_updated_by = type_policies.get(type_policy).get(policy_slug).get('updated_by')
                if not policy_updated_by:
                    continue
                if policy_slug in ('printers_res', 'user_shared_folder_res', 'software_sources_res'):
                    policy_slug = self.emitters_policy_slug(policy_slug)
                policy = self.get_element(policies, 'slug', policy_slug)
                if policy['is_mergeable']:
                    computer_policies[policy_slug] = {}
                    for type_update_by in policy_updated_by.keys():
                        if type_update_by in ('ou', 'group', 'users'):
                            computer_policies[policy_slug].update({type_update_by: []})
                            for update_by in policy_updated_by.get(type_update_by):
                                node = self.get_element(objects, '_id', ObjectId(update_by))
                                computer_policies[policy_slug][type_update_by].append(node['name'])
                        else:
                            node = self.get_element(objects, '_id', ObjectId(policy_updated_by.get(type_update_by)))
                            computer_policies[policy_slug].update({'computer': node['name']})
                else:
                    node = policy_updated_by[policy_updated_by.keys()[0]]
                    if isinstance(node, list):
                        node = self.get_element(objects, '_id', ObjectId(node[0]))
                    else:
                        node = self.get_element(objects, '_id', ObjectId(node))
                    node = priority_object(computer_node, policy['path'] + '.updated_by', node, None, db.nodes)
                    computer_policies[policy_slug] = {node['type']: node['name']}
        return computer_policies

    def get_element(self, dictionary, field_title, field_content):
        for element in dictionary:
            if field_content == element[field_title]:
                return element

    def cursor_to_list(self, cursor):
        result = []
        for element in cursor:
            result.append(element)
        return result

    def emitters_policy_slug(self, policy_slug):
        if policy_slug == 'printer_res':
            return 'printer_can_view'
        elif policy_slug == 'user_shared_folder_res':
            return 'storage_can_view'
        else:
            return 'repository_can_view'
