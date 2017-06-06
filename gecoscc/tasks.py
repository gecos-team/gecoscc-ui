#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#   Pablo Iglesias <pabloig90@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import datetime
import random
import os
import subprocess

from copy import deepcopy

from bson import ObjectId

from chef import Node, Client
from chef.node import NodeAttributes

from celery.task import Task, task
from celery.signals import task_prerun
from celery.exceptions import Ignore
from jsonschema import validate
from jsonschema.exceptions import ValidationError


import gettext
from gecoscc.eventsmanager import JobStorage
from gecoscc.rules import get_rules, is_user_policy, get_username_chef_format, object_related_list
from gecoscc.socks import invalidate_jobs
# It is necessary import here: apply_policies_to_computer, apply_policies_to_printer and apply_policies_to_user...
from gecoscc.utils import (get_chef_api, get_cookbook,
                           get_filter_nodes_belonging_ou,
                           emiter_police_slug, get_computer_of_user,
                           delete_dotted, to_deep_dict, reserve_node_or_raise,
                           save_node_and_free, NodeBusyException, NodeNotLinked,
                           apply_policies_to_computer, apply_policies_to_user,
                           apply_policies_to_printer, apply_policies_to_storage,
                           apply_policies_to_repository, apply_policies_to_group,
                           apply_policies_to_ou, recursive_defaultdict, setpath, dict_merge,
                           RESOURCES_RECEPTOR_TYPES, RESOURCES_EMITTERS_TYPES, POLICY_EMITTER_SUBFIX,
                           get_policy_emiter_id, get_object_related_list, update_computers_of_user)


DELETED_POLICY_ACTION = 'deleted'
SOFTWARE_PROFILE_SLUG = 'package_profile_res'


class ChefTask(Task):
    abstract = True

    def __init__(self):
        self.init_jobid()
        self.logger = self.get_logger()
        localedir = os.path.join(os.path.dirname(__file__), 'locale')
        gettext.bindtextdomain('gecoscc', localedir)
        gettext.textdomain('gecoscc')
        self._ = gettext.gettext
        
        
    @property
    def db(self):
        if hasattr(self, '_db'):
            return self._db
        return self.app.conf.get('mongodb').get_database()

    def log(self, messagetype, message):
        assert messagetype in ('debug', 'info', 'warning', 'error', 'critical')
        op = getattr(self.logger, messagetype)
        op('[{0}] {1}'.format(self.jid, message))

    def init_jobid(self):
        if getattr(self, 'request', None) is not None:
            self.jid = self.request.id
        else:
            self.jid = unicode(ObjectId())

    def walking_here(self, obj, related_objects):
        '''
        Checks if an object is in the object related list else add it to the list
        '''
        if related_objects is not None:
            if obj not in related_objects:
                related_objects.append(deepcopy(obj))
            else:
                return True
        return False

    def get_related_computers_of_computer(self, obj, related_computers, related_objects):
        '''
        Get the related computers of a computer
        '''
        if self.walking_here(obj, related_objects):
            return related_computers
        related_computers.append(obj)
        return related_computers

    def get_related_computers_of_group(self, obj, related_computers, related_objects):
        '''
        Get the related computers of a group
        '''
        if self.walking_here(obj, related_objects):
            return related_computers
        for node_id in obj['members']:
            node = self.db.nodes.find_one({'_id': node_id})
            if node and node not in related_objects:
                self.get_related_computers(node, related_computers, related_objects)
        return related_computers

    def get_related_computers_of_ou(self, ou, related_computers, related_objects):
        '''
        Get the related computers of an OU
        '''
        if self.walking_here(ou, related_objects):
            return related_computers
        computers = self.db.nodes.find({'path': get_filter_nodes_belonging_ou(ou['_id']),
                                        'type': 'computer'})
        for computer in computers:
            self.get_related_computers_of_computer(computer,
                                                   related_computers,
                                                   related_objects)

        users = self.db.nodes.find({'path': get_filter_nodes_belonging_ou(ou['_id']),
                                    'type': 'user'})
        for user in users:
            self.get_related_computers_of_user(user,
                                               related_computers,
                                               related_objects)

        groups = self.db.nodes.find({'path': get_filter_nodes_belonging_ou(ou['_id']),
                                     'type': 'group'})
        for group in groups:
            self.get_related_computers_of_group(group,
                                                related_computers,
                                                related_objects)

        return related_computers

    def get_related_computers_of_emiters(self, obj, related_computers, related_objects):
        '''
        Get the related computers of emitter objects
        '''
        if self.walking_here(obj, related_objects):
            return related_computers
        object_related_list = get_object_related_list(self.db, obj)
        for object_related in object_related_list:
            self.get_related_computers(object_related, related_computers, related_objects)
        return related_computers

    def get_related_computers_of_user(self, obj, related_computers, related_objects):
        '''
        Get the related computer of User
        '''
        if self.walking_here(obj, related_objects):
            return related_computers
        return get_computer_of_user(self.db.nodes, obj, related_computers)

    def get_related_computers(self, obj, related_computers=None, related_objects=None):
        '''
        Get the related computers with the objs
        '''
        if related_objects is None:
            related_objects = []

        if related_computers is None:
            related_computers = []

        obj_type = obj['type']

        if obj['type'] in RESOURCES_EMITTERS_TYPES:
            obj_type = 'emiters'
        get_realted_computers_of_type = getattr(self, 'get_related_computers_of_%s' % obj_type)
        return get_realted_computers_of_type(obj, related_computers, related_objects)

    def is_updating_policies(self, obj, objold):
        '''
        Checks if the not mergeable policy has changed or is equal to the policy stored in the node chef.
        '''
        new_policies = obj.get('policies', {})
        new_memberof = obj.get('memberof', {})
        if objold is None:
            old_policies = {}
            old_memberof = {}
        else:
            old_policies = objold.get('policies', {})
            old_memberof = objold.get('memberof', {})
        return new_policies != old_policies or new_memberof != old_memberof

    def is_updated_node(self, obj, objold):
        '''
        Chef if an objects is updated in node
        '''
        return obj != objold

    def get_object_ui(self, rule_type, obj, node, policy):
        '''
        Get the object
        '''
        if obj == {}:
            return {}
        if rule_type == 'save':
            if policy.get('is_emitter_policy', False):
                obj = self.db.nodes.find_one({'node_chef_id': node.name})
            return obj
        elif rule_type == 'policies':
            policy_id = unicode(policy['_id'])
            if policy.get('is_emitter_policy', False):
                if not obj.get(rule_type, None):
                    object_related_id_list = []
                else:
                    object_related_id_list = obj[rule_type][policy_id]['object_related_list']
                object_related_list = []
                for object_related_id in object_related_id_list:
                    if policy['slug'] == SOFTWARE_PROFILE_SLUG:
                        object_related = self.db.software_profiles.find_one({'_id': ObjectId(object_related_id)})
                        object_related['type'] = 'software_profile'
                    else:
                        object_related = self.db.nodes.find_one({'_id': ObjectId(object_related_id)})
                    if not object_related:
                        continue
                    object_related_list.append(object_related)
                return {'object_related_list': object_related_list,
                        'type': policy['slug'].replace(POLICY_EMITTER_SUBFIX, '')}
            else:
                try:
                    return obj[rule_type][policy_id]
                except KeyError:
                    return {}
        return ValueError("The rule type should be save or policy")

    def get_rules_and_object(self, rule_type, obj, node, policy):
        '''
        Get the rules and object
        '''
        if rule_type == 'save':
            rules = get_rules(obj['type'], rule_type, node, policy)
            obj = self.get_object_ui(rule_type, obj, node, policy)
            if not obj:
                rules = {}
            return (rules, obj)
        elif rule_type == 'policies':
            rules = get_rules(obj['type'], rule_type, node, policy)
            return (rules,
                    self.get_object_ui(rule_type, obj, node, policy))
        return ValueError("The rule type should be save or policy")

    def get_related_objects(self, nodes_ids, policy, obj_type):
        '''
        Get related objects from a emitter policy
        '''
        new_field_chef_value = []
        updater_nodes = self.db.nodes.find({"$or": [{'_id': {"$in": nodes_ids}}]})

        for updater_node in updater_nodes:
            if unicode(policy['_id']) in updater_node['policies']:
                new_field_chef_value += updater_node['policies'][unicode(policy['_id'])]['object_related_list']

        new_field_chef_value = list(set(new_field_chef_value))
        self.log("debug","tasks.py:::get_related_objects -> new_field_chef_value = {0}".format(new_field_chef_value))
        related_objects = []

        for node_id in new_field_chef_value:
            if obj_type == SOFTWARE_PROFILE_SLUG:
                related_objs = self.db.software_profiles.find_one({'_id': ObjectId(node_id)})
                related_objs.update({'type': 'software_profile'})
                obj_list = {'object_related_list': [related_objs], 'type': obj_type}
            else:
                related_objs = self.db.nodes.find_one({'_id': ObjectId(node_id)})
                obj_list = {'object_related_list': [related_objs], 'type': obj_type}
            related_objects += object_related_list(obj_list)
        self.log("debug","tasks.py:::get_related_objects -> related_objects = {0}".format(related_objects))
        return related_objects

    def get_nodes_ids(self, nodes_updated_by):
        '''
        Get the nodes ids
        '''
        nodes_ids = []
        for node_type, updated_by_id in nodes_updated_by:
            if isinstance(updated_by_id, list):
                nodes_ids += [ObjectId(node_id) for node_id in updated_by_id]
            else:
                nodes_ids.append(ObjectId(updated_by_id))
        return nodes_ids

    def remove_duplicated_dict(self, new_field_chef_value):
        '''
        Remove duplicate elements from a list of dictionaries
        '''
        new_field_chef_dict = []
        for field_value in new_field_chef_value:
            if field_value not in new_field_chef_dict:
                new_field_chef_dict.append(field_value)

        return new_field_chef_dict

    def has_changed_ws_policy(self, node, obj_ui, field_ui, field_chef):
        '''
        Checks if the ws policy has changed or is equal to the policy stored in the node chef.
        '''
        field_chef_value = node.attributes.get_dotted(field_chef)
        for obj in obj_ui[field_ui]:
            if isinstance(field_chef_value, list):
                if obj not in field_chef_value:
                    return True
        return False

    def has_changed_user_policy(self, node, obj_ui, field_ui, field_chef, priority_obj, priority_obj_ui):
        '''
        Checks if the user policy has changed or is equal to the policy stored in the node chef.
        '''
        field_chef_value = node.attributes.get_dotted(field_chef)
        for policy_type in obj_ui.keys():
            if isinstance(field_chef_value.get(priority_obj['name']).get(policy_type), list) or field_chef_value.get(priority_obj['name']).get(policy_type) is None:
                if field_chef_value.get(priority_obj['name']).get(policy_type) is None:
                    return True
                elif obj_ui.get(policy_type) != []:
                    for obj in obj_ui.get(policy_type):
                            if obj not in field_chef_value.get(priority_obj['name']).get(policy_type):
                                return True
        return False

    def has_changed_ws_emitter_policy(self, node, obj_ui, field_chef):
        '''
        Checks if the workstation emitter policy has changed or is equal to the policy stored in the node chef.
        This policy is emitter, that is that the policy contains related objects (software profiles, printers and repositories)
        '''
        field_chef_value = node.attributes.get_dotted(field_chef)

        if obj_ui.get('object_related_list', False):
            related_objs = obj_ui['object_related_list']
            for related_obj in related_objs:
                if obj_ui['type'] == SOFTWARE_PROFILE_SLUG:
                    for obj_field in related_obj['packages']:
                        if obj_field not in field_chef_value:
                            return True

                elif obj_ui['type'] == 'repository':
                    if not any(d['repo_name'] == related_obj['name'] for d in field_chef_value):
                        return True

                elif not any(d['name'] == related_obj['name'] for d in field_chef_value):
                    return True
            return False
        related_objs = obj_ui
        for field_value in field_chef_value:
            if obj_ui['type'] == 'repository':
                field_chef = field_value['repo_name']
            else:
                field_chef = field_value['name']
            if related_objs['name'] == field_chef:
                for attribute in field_value.keys():
                    if attribute == 'repo_name':
                        if related_objs['name'] != field_value[attribute]:
                            return True
                    elif related_objs[attribute] != field_value[attribute]:
                        return True
        return False

    def has_changed_user_emitter_policy(self, node, obj_ui, field_ui, field_chef, priority_obj, priority_obj_ui):
        '''
        Checks if the user emitter policy has changed or is equal to the policy stored in the node chef.
        This policy is emitter, that is that the policy contains related objects (storage)
        '''
        field_chef_value = node.attributes.get_dotted(field_chef)
        field_chef_value_storage = field_chef_value.get(priority_obj['name']).get('gtkbookmarks')
        if obj_ui.get('object_related_list', False):
            related_objects = obj_ui['object_related_list']
            if field_chef_value_storage:
                for obj in related_objects:
                    if not any(d['name'] == obj['name'] for d in field_chef_value_storage):
                        return True
                return False
            return True

        related_objects = obj_ui
        for field_value in field_chef_value_storage:
            if related_objects['name'] == field_value['name']:
                for attribute in field_value.keys():
                    if related_objects[attribute] != field_value[attribute]:
                        return True
        return False

    def update_ws_mergeable_policy(self, node, action, field_chef, field_ui, policy, update_by_path, obj_ui):
        '''
        Updates node chef with a mergeable workstation policy
        '''
        self.log("debug","tasks.py:::update_ws_mergeable_policy - field_chef = {0}".format(field_chef))
        if self.has_changed_ws_policy(node, obj_ui, field_ui, field_chef) or action == DELETED_POLICY_ACTION:
           
            node_updated_by = node.attributes.get_dotted(update_by_path).items()
            self.log("debug","tasks.py:::update_ws_mergeable_policy - node_updated_by = {0}".format(node_updated_by))
            nodes_ids = self.get_nodes_ids(node_updated_by)
            self.log("debug","tasks.py:::update_ws_mergeable_policy - nodes_ids = {0}".format(nodes_ids))
        

            new_field_chef_value = []
            self.log("debug","tasks.py:::update_ws_mergeable_policy - new_field_chef_value = {0}".format(new_field_chef_value))
            updater_nodes = self.db.nodes.find({"$or": [{'_id': {"$in": nodes_ids}}]})
            for updater_node in updater_nodes:
                if field_ui in updater_node['policies'][unicode(policy['_id'])]:                                                                
                    new_field_chef_value += updater_node['policies'][unicode(policy['_id'])][field_ui]
                else: # support_os
                    new_field_chef_value += obj_ui[field_ui]

            
            try:
                node.attributes.set_dotted(field_chef,list(set(new_field_chef_value)))
            except TypeError:
                new_field_chef_value = self.remove_duplicated_dict(new_field_chef_value)
                node.attributes.set_dotted(field_chef, new_field_chef_value)
            return True
   
        return False
            

    def update_user_mergeable_policy(self, node, action, field_chef, field_ui, policy, priority_obj, priority_obj_ui, update_by_path, obj_ui):
        '''
        Updates node chef with a mergeable user policy
        '''
        if self.has_changed_user_policy(node, obj_ui, field_ui, field_chef, priority_obj, priority_obj_ui) or action == DELETED_POLICY_ACTION:
            node_updated_by = node.attributes.get_dotted(update_by_path).items()
            nodes_ids = self.get_nodes_ids(node_updated_by)
            self.log("debug","tasks.py:::update_user_mergeable_policy - nodes_ids = {0}".format(nodes_ids))

            new_field_chef_value = {}
            updater_nodes = self.db.nodes.find({"$or": [{'_id': {"$in": nodes_ids}}]})
            for updater_node in updater_nodes:
                node_policy = updater_node['policies'][unicode(policy['_id'])]
                for policy_field in node_policy.keys():
                    if policy_field not in new_field_chef_value:
                        new_field_chef_value[policy_field] = []
                    new_field_chef_value[policy_field] += node_policy[policy_field]
                

            obj_ui_field = field_ui(priority_obj_ui, obj=priority_obj, node=node, field_chef=field_chef)
            if obj_ui_field.get(priority_obj['name']):
                for policy_field in policy['schema']['properties'].keys():
                    obj_ui_field.get(priority_obj['name'])[policy_field] = new_field_chef_value[policy_field]
            else:
                return False
        
            node.attributes.set_dotted(field_chef, obj_ui_field)
            return True

        return False

    def update_ws_emitter_policy(self, node, action, policy, obj_ui_field, field_chef, obj_ui, update_by_path):
        '''
        Update node chef with a mergeable workstation emitter policy
        This policy is emitter, that is that the policy contains related objects (software profiles, printers and repositories)
        '''
        if self.has_changed_ws_emitter_policy(node, obj_ui, field_chef) or action == DELETED_POLICY_ACTION:
            node_updated_by = node.attributes.get_dotted(update_by_path).items()
            nodes_ids = self.get_nodes_ids(node_updated_by)

            related_objects = self.get_related_objects(nodes_ids, policy, obj_ui['type'])

            node.attributes.set_dotted(field_chef, related_objects)
            return True

        return False
        

    def update_user_emitter_policy(self, node, action, policy, obj_ui_field, field_chef, obj_ui, priority_obj, priority_obj_ui, field_ui, update_by_path):
        '''
        Update node chef with a mergeable user emitter policy
        This policy is emitter, that is that the policy contains related objects (storage)
        '''
        if self.has_changed_user_emitter_policy(node, obj_ui, field_ui, field_chef, priority_obj, priority_obj_ui) or action == DELETED_POLICY_ACTION:
            node_updated_by = node.attributes.get_dotted(update_by_path).items()
            nodes_ids = self.get_nodes_ids(node_updated_by)

            related_objects = self.get_related_objects(nodes_ids, policy, obj_ui['type'])
            current_objs = field_ui(priority_obj_ui, obj=priority_obj, node=node, field_chef=field_chef)

            for objs in related_objects:
                if objs not in current_objs.get(priority_obj['name']).get('gtkbookmarks'):
                    current_objs.get(priority_obj['name'])['gtkbookmarks'].append(objs)
            node.attributes.set_dotted(field_chef, current_objs)
            return True

        return False
        

    def update_node_from_rules(self, rules, user, computer, obj_ui, obj, action, node, policy, rule_type, parent_id, job_ids_by_computer):
        '''
        This function update a node from rules.
        Rules are the different fields in a policy.
        We have different cases:
            1 - The field is None and action is different to remove
            2 - The field is None and action is remove
            3 - The policy is not mergeable
            4 - The policy is mergeable
        '''
        updated = updated_updated_by = False
        attributes_jobs_updated = []
        attributes_updated_by_updated = []
        is_mergeable = policy.get('is_mergeable', False)
        for field_chef, field_ui in rules.items():
            if is_user_policy(field_chef) and 'user' not in computer:
                continue
            job_attr = '.'.join(field_chef.split('.')[:3]) + '.job_ids'
            updated_by_attr = self.get_updated_by_fieldname(field_chef, policy, obj, computer)
            priority_obj_ui = obj_ui
            obj_ui_field = None
            if (rule_type == 'policies' or not policy.get('is_emitter_policy', False)) and updated_by_attr not in attributes_updated_by_updated:
                updated_updated_by = updated_updated_by or self.update_node_updated_by(node, field_chef, obj, action, updated_by_attr, attributes_updated_by_updated)
            priority_obj = self.priority_object(node, updated_by_attr, obj, action)

            if priority_obj != obj:
                priority_obj_ui = self.get_object_ui(rule_type, priority_obj, node, policy)
            if priority_obj.get('_id', None) == obj.get('_id', None) or action == DELETED_POLICY_ACTION or is_mergeable:
                if callable(field_ui):
                    if is_user_policy(field_chef):
                        priority_obj = computer['user']
                    obj_ui_field = field_ui(priority_obj_ui, obj=priority_obj, node=node, field_chef=field_chef)
                else:
                    # Policy fields that are not sent in the form are populated with their defaults
                    obj_ui_field = priority_obj_ui.get(field_ui, node.default.get_dotted(field_chef))
                    self.log("debug","tasks:::update_node_from_rules -> obj_ui_field = {0}".format(obj_ui_field))
                    if field_ui not in obj_ui:
                        obj_ui[field_ui] = node.default.get_dotted(field_chef)
                        self.log("debug","tasks:::update_node_from_rules - obj_ui = {0}".format(obj_ui))

                if not obj_ui_field and action == DELETED_POLICY_ACTION:
                    try:
                        obj_ui_field = delete_dotted(node.attributes, field_chef)
                        updated = True
                    except KeyError:
                        pass

                elif not is_mergeable:
                    try:
                        value_field_chef = node.attributes.get_dotted(field_chef)
                    except KeyError:
                        value_field_chef = None

                    if obj_ui_field != value_field_chef:
                        node.attributes.set_dotted(field_chef, obj_ui_field)
                        updated = True

                elif is_mergeable:
                    update_by_path = self.get_updated_by_fieldname(field_chef, policy, obj, computer)



                    if obj_ui.get('type', None) == 'storage':
                        is_policy_updated = self.update_user_emitter_policy(node, action, policy, obj_ui_field, field_chef, obj_ui, priority_obj, priority_obj_ui, field_ui, update_by_path)
                    elif obj_ui.get('type', None) in ['printer', 'repository', SOFTWARE_PROFILE_SLUG]:
                        is_policy_updated = self.update_ws_emitter_policy(node, action, policy, obj_ui_field, field_chef, obj_ui, update_by_path)
                    elif not is_user_policy(field_chef):
                        is_policy_updated = self.update_ws_mergeable_policy(node, action, field_chef, field_ui, policy, update_by_path, obj_ui)
                    elif is_user_policy(field_chef):
                        is_policy_updated = self.update_user_mergeable_policy(node, action, field_chef, field_ui, policy, priority_obj, priority_obj_ui, update_by_path, obj_ui)

                    if is_policy_updated:
                        updated = True
            if job_attr not in attributes_jobs_updated:
                if updated:
                    self.update_node_job_id(user, obj, action, computer, node, policy, job_attr, attributes_jobs_updated, parent_id, job_ids_by_computer)
        return (node, (updated or updated_updated_by))

    def get_first_exists_node(self, ids, obj, action):
        '''
        Get the first exising node from a ids list
        '''
        for mongo_id in ids:
            node = self.db.nodes.find_one({'_id': ObjectId(mongo_id)})
            if node:
                if action != DELETED_POLICY_ACTION or unicode(obj.get('_id')) != mongo_id:
                    return node
        return {}

    def get_updated_by_fieldname(self, field_chef, policy, obj, computer):
        '''
        Get the path of updated_by field
        '''
        updated_path = '.'.join(field_chef.split('.')[:3])
        if is_user_policy(field_chef):
            if obj['type'] != 'user':
                user = computer['user']
            else:
                user = obj
            updated_path += '.users.' + get_username_chef_format(user)
        updated_path += '.updated_by'
        return updated_path

    def priority_object(self, node, updated_by_fieldname, obj, action):
        '''
        Get the priority from an object
        '''
        if obj['type'] in ['computer', 'user'] and action != DELETED_POLICY_ACTION:
            return obj
        try:
            updated_by = node.attributes.get_dotted(updated_by_fieldname).to_dict()
        except KeyError:
            updated_by = {}
        if not updated_by:
            if action == DELETED_POLICY_ACTION:
                return {}
            else:
                return obj
        priority_object = {}

        if updated_by.get('computer', None):
            if action != DELETED_POLICY_ACTION or unicode(obj.get('_id')) != updated_by['computer']:
                priority_object = self.db.nodes.find_one({'_id': ObjectId(updated_by['computer'])})
        if not priority_object and updated_by.get('user', None):
            if action != DELETED_POLICY_ACTION or unicode(obj.get('_id')) != updated_by['user']:
                priority_object = self.db.nodes.find_one({'_id': ObjectId(updated_by['user'])})
        if not priority_object and updated_by.get('group', None):
            priority_object = self.get_first_exists_node(updated_by.get('group', None), obj, action)
        if not priority_object and updated_by.get('ou', None):
            priority_object = self.get_first_exists_node(updated_by.get('ou', None), obj, action)
        return priority_object

    def update_node_updated_by(self, node, field_chef, obj, action, attr, attributes_updated):
        '''
        Updates the updated_by field of a node
        '''
        updated = False
        try:
            updated_by = node.attributes.get_dotted(attr).to_dict()
        except KeyError:
            updated_by = {}
        obj_id = unicode(obj['_id'])
        obj_type = obj['type']
        if obj_type in ['computer', 'user']:
            if action == DELETED_POLICY_ACTION:
                del updated_by[obj_type]
            else:
                updated_by[obj_type] = obj_id
            updated = True
        else:  # Ous or groups
            updated_by_type = updated_by.get(obj_type, [])
            if action == DELETED_POLICY_ACTION:
                try:
                    updated_by_type.remove(obj_id)
                    updated = True
                except ValueError:
                    pass
            elif obj_id not in updated_by_type:
                updated = True
                if obj_type == 'ou':
                    updated_by_type.append(obj_id)
                    updated_by_type = self.order_ou_by_depth(updated_by_type)
                else:
                    updated_by_type.append(obj_id)
            if updated_by_type:
                updated_by[obj_type] = updated_by_type
            elif obj_type in updated_by:
                del updated_by[obj_type]
        if updated:
            if is_user_policy(attr):
                users_dict_path = '.'.join(attr.split('.')[:-2])
                try:
                    if not node.attributes.get_dotted(users_dict_path):
                        node.attributes.set_dotted(users_dict_path, {})
                except KeyError:
                    node.attributes.set_dotted(users_dict_path, {})
            node.attributes.set_dotted(attr, updated_by)
            attributes_updated.append(attr)
        return updated

    def order_ou_by_depth(self, ou_ids):
        '''
        order ous by depth
        '''
        ou_ids = [ObjectId(ou_id) for ou_id in ou_ids]
        ous = [ou for ou in self.db.nodes.find({'_id': {'$in': ou_ids}})]
        ous.sort(key=lambda x: x['path'].count(','), reverse=True)
        return [unicode(ou['_id']) for ou in ous]

    def update_node_job_id(self, user, obj, action, computer, node, policy, attr, attributes_updated, parent_id, job_ids_by_computer):
        '''
        Update the jobs field of a node
        '''
        if node.attributes.has_dotted(attr):
            job_ids = node.attributes.get_dotted(attr)
        else:
            job_ids = []
        job_storage = JobStorage(self.db.jobs, user)
        job_status = 'processing'
        computer_name = computer['name']
        if is_user_policy(policy.get('path', '')) and 'user' in computer:
            computer['user_and_name'] = '%s / %s' % (computer_name, computer['user']['name'])
        else:
            computer['user_and_name'] = None
        job_id = job_storage.create(obj=obj,
                                    op=action,
                                    status=job_status,
                                    computer=computer,
                                    policy=policy,
                                    parent=parent_id,
                                    administrator_username=user['username'])
        job_ids.append(unicode(job_id))
        job_ids_by_computer.append(job_id)
        attributes_updated.append(attr)
        node.attributes.set_dotted(attr, job_ids)

    def disassociate_object_from_group(self, obj):
        '''
        Disassociate object from a group
        '''
        groups = self.db.nodes.find({'type': 'group', 'members': obj['_id']})
        for g in groups:
            self.db.nodes.update({
                '_id': g['_id']
            }, {
                '$pull': {
                    'members': obj['_id']
                }
            }, multi=False)

    def get_policies(self, rule_type, action, obj, objold):
        '''
        Get the policies to apply and the policies to remove from an object
        '''
        policies_apply = [(policy_id, action) for policy_id in obj[rule_type].keys()]
        if not objold:
            return policies_apply
        policies_delete = set(objold[rule_type].keys()) - set(obj[rule_type].keys())
        policies_delete = [(policy_id, DELETED_POLICY_ACTION) for policy_id in policies_delete]
        return policies_apply + policies_delete

    def update_node(self, user, computer, obj, objold, node, action, parent_id, job_ids_by_computer, force_update):
        '''
        This method update the node with changed or created actions.
        Have two different cases:
            1 - object type is ou, user, computer or group.
            2 - object type is emitter: printer, storage or repository
        '''
        updated = False
        if action == DELETED_POLICY_ACTION or action == 'detached':
            return(node, False)
        if action not in ['changed', 'created']:
            raise ValueError('The action should be changed or created')
        if obj['type'] in RESOURCES_RECEPTOR_TYPES:  # ou, user, comp, group
            if force_update or self.is_updating_policies(obj, objold):
                rule_type = 'policies'
                for policy_id, action in self.get_policies(rule_type, action, obj, objold):
                    policy = self.db.policies.find_one({"_id": ObjectId(policy_id)})
                    if action == DELETED_POLICY_ACTION:
                        rules, obj_ui = self.get_rules_and_object(rule_type, objold, node, policy)
                    else:
                        rules, obj_ui = self.get_rules_and_object(rule_type, obj, node, policy)
                    node, updated_policy = self.update_node_from_rules(rules, user, computer, obj_ui, obj, action, node, policy, rule_type, parent_id, job_ids_by_computer)
                    if not updated and updated_policy:
                        updated = True
            return (node, updated)
        elif obj['type'] in RESOURCES_EMITTERS_TYPES:  # printer, storage, repository
            rule_type = 'save'
            if force_update or self.is_updated_node(obj, objold):
                policy = self.db.policies.find_one({'slug': emiter_police_slug(obj['type'])})
                rules, obj_receptor = self.get_rules_and_object(rule_type, obj, node, policy)
                node, updated = self.update_node_from_rules(rules, user, computer, obj, obj_receptor, action, node, policy, rule_type, job_ids_by_computer)
            return (node, updated)

    def validate_data(self, node, cookbook, api):
        '''
        Useful method, validate the DATABASES
        '''
        try:
            schema = cookbook['metadata']['attributes']['json_schema']['object']
            validate(to_deep_dict(node.attributes), schema)
        except ValidationError as e:
            # Bugfix: Validation error "required property"
            # example:
            # u'boot_lock_res' is a required property Failed validating
            if 'is a required property' in e.message:
                self.log('debug',"validation error: e.validator_value = {0}".format(e.validator_value))
                # e.path: deque
                for required_field in e.validator_value:
                    e.path.append(required_field)
                    self.log('debug',"validation error: path = {0}".format(e.path))

                    # Required fields initialization
                    attr_type = e.schema['properties'][required_field]['type']
                    if  attr_type == 'array':
                        initial_value = []
                    elif attr_type == 'object':
                        initial_value = {}
                    elif attr_type == 'string':
                        initial_value = ''
                    elif attr_type == 'number':
                        initial_value = 0

                    # Making required fields dictionary
                    # example: {u'gecos_ws_mgmt': {u'sotfware_mgmt': {u'package_res':{u'new_field':[]}}}}
                    required_dict = recursive_defaultdict()
                    setpath(required_dict, list(e.path), initial_value)
                    self.log('debug',"validation error: required_dict = {0}".format(required_dict))

                    # node.default: default chef attributes
                    defaults_dict = node.default.to_dict()

                    # merging defaults with new required fields
                    merge_dict = dict_merge(defaults_dict,required_dict)
                    self.log('debug',"validation error: merge_dict = {0}".format(merge_dict))

                    # setting new default attributes
                    setattr(node,'default',NodeAttributes(merge_dict))

                    # Saving node
                    save_node_and_free(node)

                    # reset variables next iteration
                    del required_dict, defaults_dict, merge_dict
                    e.path.pop()


    def report_error(self, exception, job_ids, computer, prefix=None):
        '''
        if an error is produced, save the error in the job
        '''
        message = 'No save in chef server.'
        if prefix:
            message = "%s %s" % (prefix, message)
        message = "%s %s" % (message, unicode(exception))
        for job_id in job_ids:
            self.db.jobs.update(
                {'_id': job_id},
                {'$set': {'status': 'errors',
                          'message': message,
                          'last_update': datetime.datetime.utcnow()}})
        if not computer.get('error_last_saved', False):
            self.db.nodes.update({'_id': computer['_id']},
                                 {'$set': {'error_last_saved': True}})

    def report_node_not_linked(self, computer, user, obj, action):
        '''
        if the node is not linked, report node not linked error
        '''
        message = 'No save in chef server. The node is not linked, it is possible that this node was imported from AD or LDAP'
        self.report_generic_error(user, obj, action, message, computer, status='warnings')

    def report_node_busy(self, computer, user, obj, action):
        '''
        if the node is busy, report node busy error
        '''
        message = 'No save in chef server. The node is busy'
        self.report_generic_error(user, obj, action, message, computer)

    def report_unknown_error(self, exception, user, obj, action, computer=None):
        '''
        Report unknown error
        '''
        message = 'No save in chef server. %s' % unicode(exception)
        self.report_generic_error(user, obj, action, message, computer)

    def report_generic_error(self, user, obj, action, message, computer=None, status='errors'):
        '''
        Report generic error
        '''
        job_storage = JobStorage(self.db.jobs, user)
        job_status = status
        job = dict(obj=obj,
                   op=action,
                   status=job_status,
                   message=message,
                   administrator_username=user['username'])
        if computer:
            job['computer'] = computer
        job_storage.create(**job)

    def object_action(self, user, obj, objold=None, action=None, computers=None):
        '''
        This method try to get the node to make changes in it.
        Theses changes are called actions and can be: changed, created, moved and deleted.
        if the node is free, the method can get the node, it reserves the node and runs the action, later the node is saved and released.
        '''
        api = get_chef_api(self.app.conf, user)
        cookbook = get_cookbook(api, self.app.conf.get('chef.cookbook_name'))
        computers = computers or self.get_related_computers(obj)
        # MacroJob
        job_ids_by_order = []
        name = "%s %s" % (obj['type'], action)
        self.log("debug","obj_type_translate {0}".format(obj['type']))
        self.log("debug","action_translate {0}".format(action))
        name_es = self._(action) + " " + self._(obj['type'])
        macrojob_storage = JobStorage(self.db.jobs, user)
        macrojob_id = macrojob_storage.create(obj=obj,
                                    op=action,
                                    computer=None,
                                    status='processing',
                                    policy={'name':name,'name_es':name_es},
                                    administrator_username=user['username'])
        invalidate_jobs(self.request, user)
        are_new_jobs = False
        for computer in computers:
            try:
                job_ids_by_computer = []
                node_chef_id = computer.get('node_chef_id', None)
                node = reserve_node_or_raise(node_chef_id, api, 'gcc-tasks-%s-%s' % (obj['_id'], random.random()), 10)
                if not node.get(self.app.conf.get('chef.cookbook_name')):
                    raise NodeNotLinked("Node %s is not linked" % node_chef_id)
                error_last_saved = computer.get('error_last_saved', False)
                error_last_chef_client = computer.get('error_last_chef_client', False)
                force_update = error_last_saved or error_last_chef_client
                node, updated = self.update_node(user, computer, obj, objold, node, action, macrojob_id, job_ids_by_computer, force_update)
                if job_ids_by_computer:
                    job_ids_by_order += job_ids_by_computer
                if not updated:
                    save_node_and_free(node)
                    continue
                are_new_jobs = True
                self.validate_data(node, cookbook, api)
                save_node_and_free(node)
                if error_last_saved:
                    self.db.nodes.update({'_id': computer['_id']},
                                         {'$set': {'error_last_saved': False}})
            except NodeNotLinked as e:
                self.report_node_not_linked(computer, user, obj, action)
                are_new_jobs = True
                save_node_and_free(node, api, refresh=True)
            except NodeBusyException as e:
                self.report_node_busy(computer, user, obj, action)
                are_new_jobs = True
            except ValidationError as e:
                if not job_ids_by_computer:
                    self.report_unknown_error(e, user, obj, action, computer)
                self.report_error(e, job_ids_by_computer, computer, 'Validation error: ')
                save_node_and_free(node, api, refresh=True)
                are_new_jobs = True
            except Exception as e:
                if not job_ids_by_computer:
                    self.report_unknown_error(e, user, obj, action, computer)
                self.report_error(e, job_ids_by_computer, computer)
                try:
                    save_node_and_free(node, api, refresh=True)
                except:
                    pass
                are_new_jobs = True
        job_status = 'processing' if job_ids_by_order else 'finished'
        self.db.jobs.update({'_id': macrojob_id},
                            {'$set': {'status': job_status,
                                      'childs':  len(job_ids_by_order),
                                      'counter': len(job_ids_by_order),
                                      'message': self._("Pending: %d") % len(job_ids_by_order)}})
        if are_new_jobs:
            invalidate_jobs(self.request, user)

    def object_created(self, user, objnew, computers=None):
        self.object_action(user, objnew, action='created', computers=computers)

    def object_changed(self, user, objnew, objold, action, computers=None):
        self.object_action(user, objnew, objold, action, computers=computers)

    def object_deleted(self, user, obj, computers=None):
        obj_without_policies = deepcopy(obj)
        obj_without_policies['policies'] = {}
        object_changed = getattr(self, '%s_changed' % obj['type'])
        object_changed(user, obj_without_policies, obj, action='deleted', computers=computers)

    def object_detached(self, user, obj, computers=None):
        obj_without_policies = deepcopy(obj)
        obj_without_policies['policies'] = {}
        object_changed = getattr(self, '%s_changed' % obj['type'])
        object_changed(user, obj_without_policies, obj, action='detached', computers=computers)
        
    def object_moved(self, user, objnew, objold):
        api = get_chef_api(self.app.conf, user)
        try:
            func = globals()['apply_policies_to_%s' % objnew['type']]
        except KeyError:
            raise NotImplementedError
        func(self.db.nodes, objnew, user, api, initialize=True, use_celery=False, policies_collection=self.db.policies)

    def object_emiter_deleted(self, user, obj, computers=None):
        name = "%s deleted" % obj['type']
        name_es = self._("deleted") + " " + self._(obj['type'])
        macrojob_storage = JobStorage(self.db.jobs, user)
        macrojob_id = macrojob_storage.create(obj=obj,
                                    op='deleted',
                                    computer=None,
                                    status='finished',
                                    policy={'name':name,'name_es':name_es},
                                    childs=0,
                                    counter=0,
                                    message="Pending: 0",
                                    administrator_username=user['username'])
        invalidate_jobs(self.request, user)
        
        obj_id = unicode(obj['_id'])
        policy_id = unicode(get_policy_emiter_id(self.db, obj))
        object_related_list = get_object_related_list(self.db, obj)
        for obj_related in object_related_list:
            obj_old_related = deepcopy(obj_related)
            object_related_list = obj_related['policies'][policy_id]['object_related_list']
            if obj_id in object_related_list:
                object_related_list.remove(obj_id)
                if object_related_list:
                    self.db.nodes.update({'_id': obj_related['_id']}, {'$set': {'policies.%s.object_related_list' % policy_id: object_related_list}})
                else:
                    self.db.nodes.update({'_id': obj_related['_id']}, {'$unset': {'policies.%s' % policy_id: ""}})
                    obj_related = self.db.nodes.find_one({'_id': obj_related['_id']})
                node_changed_function = getattr(self, '%s_changed' % obj_related['type'])
                node_changed_function(user, obj_related, obj_old_related)

    def log_action(self, log_action, resource_name, objnew):
        self.log('info', '{0} {1} {2}'.format(resource_name, log_action, objnew['_id']))

    def group_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Group', objnew)

    def group_changed(self, user, objnew, objold, action='changed', computers=None):
        self.object_changed(user, objnew, objold, action, computers=computers)
        self.log_action('changed', 'Group', objnew)

    def group_moved(self, user, objnew, objold):
        self.object_moved(user, objnew, objold)
        self.log_action('moved', 'Group', objnew)

    def group_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.object_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Group', obj)

    def user_created(self, user, objnew, computers=None):
        api = get_chef_api(self.app.conf, user)
        objnew = update_computers_of_user(self.db, objnew, api)
        self.db.nodes.update({'_id': objnew['_id']},
                             {'$set': {
                                  'computers': objnew['computers'] }})

        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'User', objnew)

    def user_changed(self, user, objnew, objold, action='changed', computers=None):
        self.object_changed(user, objnew, objold, action, computers=computers)
        self.log_action('changed', 'User', objnew)

    def user_moved(self, user, objnew, objold):
        self.object_moved(user, objnew, objold)
        self.log_action('moved', 'User', objnew)

    def user_deleted(self, user, obj, computers=None, direct_deleted=True):
        if direct_deleted is False:
            self.disassociate_object_from_group(obj)
        self.object_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'User', obj)

    def computer_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Computer', objnew)

    def computer_changed(self, user, objnew, objold, action='changed', computers=None):
        self.object_changed(user, objnew, objold, action, computers=computers)
        self.log_action('changed', 'Computer', objnew)

    def computer_moved(self, user, objnew, objold):
        self.object_moved(user, objnew, objold)
        self.log_action('moved', 'Computer', objnew)

    def computer_deleted(self, user, obj, computers=None, direct_deleted=True):
        # 1 - Delete computer from chef server
        self.object_deleted(user, obj, computers=computers)
        node_chef_id = obj.get('node_chef_id', None)
        if node_chef_id:
            api = get_chef_api(self.app.conf, user)
            node = Node(node_chef_id, api)
            node.delete()
            client = Client(node_chef_id, api=api)
            client.delete()
        if direct_deleted is False:
            # 2 - Disassociate computer from its users
            users = self.db.nodes.find({'type': 'user', 'computers': obj['_id']})
            for u in users:
                self.db.nodes.update({
                    '_id': u['_id']
                }, {
                    '$pull': {
                        'computers': obj['_id']
                    }
                }, multi=False)
            # 3 - Disassociate computers from its groups
            self.disassociate_object_from_group(obj)
        self.log_action('deleted', 'Computer', obj)

    def computer_detached(self, user, obj, computers=None):
        self.object_detached(user, obj, computers=computers)
        node_chef_id = obj.get('node_chef_id', None)
        if node_chef_id:
            api = get_chef_api(self.app.conf, user)
            node = Node(node_chef_id, api)
            node.delete()
            client = Client(node_chef_id, api=api)
            client.delete()

        self.log_action('detached', 'Computer', obj)
        
    def ou_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'OU', objnew)

    def ou_changed(self, user, objnew, objold, action='changed', computers=None):
        self.object_changed(user, objnew, objold, action, computers=computers)
        self.log_action('changed', 'OU', objnew)

    def ou_moved(self, user, objnew, objold):
        self.object_moved(user, objnew, objold)
        self.log_action('moved', 'OU', objnew)

    def ou_deleted(self, user, obj, computers=None, direct_deleted=True):
        ou_path = '%s,%s' % (obj['path'], unicode(obj['_id']))
        types_to_remove = ('computer', 'user', 'group', 'printer', 'storage', 'repository', 'ou')
        for node_type in types_to_remove:
            nodes_by_type = self.db.nodes.find({'path': ou_path,
                                                'type': node_type})
            for node in nodes_by_type:
                node_deleted_function = getattr(self, '%s_deleted' % node_type)
                node_deleted_function(user, node, computers=computers, direct_deleted=False)
        self.db.nodes.remove({'path': ou_path})
        name = "%s deleted" % obj['type']
        name_es = self._("deleted") + " " + self._(obj['type'])
        macrojob_storage = JobStorage(self.db.jobs, user)
        macrojob_id = macrojob_storage.create(obj=obj,
                                    op='deleted',
                                    computer=None,
                                    status='finished',
                                    policy={'name':name,'name_es':name_es},
                                    childs=0,
                                    counter=0,
                                    message="Pending: 0",
                                    administrator_username=user['username'])
        invalidate_jobs(self.request, user)
        self.log_action('deleted', 'OU', obj)

    def printer_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Printer', objnew)

    def printer_changed(self, user, objnew, objold, action='changed', computers=None):
        self.object_changed(user, objnew, objold, action, computers=computers)
        self.log_action('changed', 'Printer', objnew)

    def printer_moved(self, user, objnew, objold):
        self.object_moved(user, objnew, objold)
        self.log_action('moved', 'Printer', objnew)

    def printer_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.object_emiter_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Printer', obj)

    def storage_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Storage', objnew)

    def storage_changed(self, user, objnew, objold, action='changed', computers=None):
        self.object_changed(user, objnew, objold, action, computers=computers)
        self.log_action('changed', 'Storage', objnew)

    def storage_moved(self, user, objnew, objold):
        self.object_moved(user, objnew, objold)
        self.log_action('moved', 'Storage', objnew)

    def storage_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.object_emiter_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Storage', obj)

    def repository_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Repository', objnew)

    def repository_changed(self, user, objnew, objold, action='changed', computers=None):
        self.object_changed(user, objnew, objold, action, computers=computers)
        self.log_action('changed', 'Repository', objnew)

    def repository_moved(self, user, objnew, objold):
        self.object_moved(user, objnew, objold)
        self.log_action('moved', 'Repository', objnew)

    def repository_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.object_emiter_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Repository', obj)


@task_prerun.connect
def init_jobid(sender, **kargs):
    """ Generate a new job id in every task run"""
    sender.init_jobid()


@task(base=ChefTask)
def task_test(value):
    self = task_test
    self.log('debug', unicode(self.db.adminusers.count()))
    return Ignore()


@task(base=ChefTask)
def object_created(user, objtype, obj, computers=None):
    self = object_created

    func = getattr(self, '{0}_created'.format(objtype), None)
    if func is not None:
        try:
            return func(user, obj, computers=computers)
        except Exception as e:
            self.report_unknown_error(e, user, obj, 'created')
            invalidate_jobs(self.request, user)
    else:
        self.log('error', 'The method {0}_created does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_changed(user, objtype, objnew, objold, action='changed', computers=None):
    self = object_changed
    func = getattr(self, '{0}_changed'.format(objtype), None)
    if func is not None:
        try:
            return func(user, objnew, objold, action, computers=computers)
        except Exception as e:
            self.report_unknown_error(e, user, objnew, 'changed')
            invalidate_jobs(self.request, user)
    else:
        self.log('error', 'The method {0}_changed does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_moved(user, objtype, objnew, objold):
    self = object_moved
    func = getattr(self, '{0}_moved'.format(objtype), None)
    if func is not None:
        try:
            return func(user, objnew, objold)
        except Exception as e:
            self.report_unknown_error(e, user, objnew, 'moved')
            invalidate_jobs(self.request, user)
    else:
        self.log('error', 'The method {0}_changed does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_deleted(user, objtype, obj, computers=None):
    self = object_changed
    func = getattr(self, '{0}_deleted'.format(objtype), None)
    if func is not None:
        try:
            return func(user, obj, computers=computers)
        except Exception as e:
            self.report_unknown_error(e, user, obj, 'deleted')
            invalidate_jobs(self.request, user)
    else:
        self.log('error', 'The method {0}_deleted does not exist'.format(
            objtype))

@task(base=ChefTask)
def object_detached(user, objtype, obj, computers=None):
    self = object_changed
    func = getattr(self, '{0}_detached'.format(objtype), None)
    if func is not None:
        try:
            return func(user, obj, computers=computers)
        except Exception as e:
            self.report_unknown_error(e, user, obj, 'deleted')
            invalidate_jobs(self.request, user)
    else:
        self.log('error', 'The method {0}_deleted does not exist'.format(
            objtype))

@task(base=ChefTask)
def cookbook_upload(user, objtype, obj, computers=None):
    self = cookbook_upload
    macrojob_storage = JobStorage(self.db.jobs, user)
    macrojob_id = macrojob_storage.create(obj=obj,
                                          op='upload',
                                          computer=None,
                                          status='processing',
                                          policy={'name':'policy uploaded','name_es': self._('policy uploaded')},
                                          administrator_username=user['username'],
                                          message=self._('policy uploading...'))

    userdir = "%s/%s/" % (self.app.conf.get('firstboot_api.media'), user['username']) 
    admincert = userdir + 'chef_user.pem'
    knifeconf = userdir + '/knife.rb'


    if not os.path.isfile(knifeconf):
       chefurl = self.app.conf.get('chef.url') + '/organizations/default'    
       textfile = """
log_level                :info
log_location             STDOUT
node_name                "%s"
client_key               "%s"
chef_server_url          "%s"
ssl_verify_mode          :verify_none
""" % (user['username'],admincert,chefurl)
     
       with open(knifeconf,'w') as file: 
           file.write(textfile)
    
    cmd_upload = self.app.conf.get('cmd_upload') % (obj['name'], obj['path'], knifeconf)
    cmd_import = self.app.conf.get('cmd_import') % (user['username'], admincert)
    self.log("debug", "tasks.py ::: cmd_upload = {0}".format(cmd_upload))
    self.log("debug", "tasks.py ::: cmd_import = {0}".format(cmd_import))

    #output_upload = subprocess.call(cmd_upload, shell=True)
    p1 = subprocess.Popen(cmd_upload, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output_upload, errors_upload = p1.communicate()

    self.log("debug", "tasks.py ::: output_upload = {0}".format(output_upload))
    self.log("debug", "tasks.py ::: errors_upload = {0}".format(errors_upload))
    if p1.returncode and errors_upload:
        status = 'errors'
        msg = errors_upload
    else:
        #output_import = subprocess.call(cmd_import, shell=True)
        p2 = subprocess.Popen(cmd_import, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        output_import, errors_import = p2.communicate()
        self.log("debug", "tasks.py ::: output_import = {0}".format(output_import))
        self.log("debug", "tasks.py ::: errors_import = {0}".format(errors_import))

        if p2.returncode and errors_import:
            status = 'errors'
            msg = errors_import
        else:
            status = 'finished'
            msg = self._("Cookbook uploaded successfully %s %s") % (obj['name'], obj['version'])
     
    self.db.jobs.update({'_id':ObjectId(macrojob_id)},{'$set':{'status':status, 'message':msg}})

    invalidate_jobs(self.request, user)   
