#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import datetime
import random

from copy import deepcopy

from bson import ObjectId

from chef import Node, Client

from celery.task import Task, task
from celery.signals import task_prerun
from celery.exceptions import Ignore
from jsonschema import validate
from jsonschema.exceptions import ValidationError


from gecoscc.eventsmanager import JobStorage
from gecoscc.rules import get_rules, is_user_policy, get_username_chef_format
from gecoscc.socks import invalidate_jobs
# It is necessary import here: apply_policies_to_computer and apply_policies_to_user
from gecoscc.utils import (get_chef_api, get_cookbook,
                           get_filter_nodes_belonging_ou,
                           emiter_police_slug, get_computer_of_user,
                           delete_dotted, to_deep_dict, reserve_node_or_raise,
                           save_node_and_free, NodeBusyException, NodeNotLinked,
                           apply_policies_to_computer, apply_policies_to_user,
                           RESOURCES_RECEPTOR_TYPES, RESOURCES_EMITTERS_TYPES,
                           POLICY_EMITTER_SUBFIX)


DELETED_POLICY_ACTION = 'deleted'
SOFTWARE_PROFILE_SLUG = 'package_profile_res'


class ChefTask(Task):
    abstract = True

    def __init__(self):
        self.init_jobid()
        self.logger = self.get_logger()

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
        if related_objects is not None:
            if obj not in related_objects:
                related_objects.append(deepcopy(obj))
            else:
                return True
        return False

    def get_related_computers_of_computer(self, obj, related_computers, related_objects):
        if self.walking_here(obj, related_objects):
            return related_computers
        related_computers.append(obj)
        return related_computers

    def get_related_computers_of_group(self, obj, related_computers, related_objects):
        if self.walking_here(obj, related_objects):
            return related_computers
        for node_id in obj['members']:
            node = self.db.nodes.find_one({'_id': node_id})
            if node and node not in related_objects:
                self.get_related_computers(node, related_computers, related_objects)
        return related_computers

    def get_related_computers_of_ou(self, ou, related_computers, related_objects):
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

    def get_policy_emiter_id(self, obj):
        return self.db.policies.find_one({'slug': emiter_police_slug(obj['type'])})['_id']

    def get_object_related_list(self, obj):
        policy_id = unicode(self.get_policy_emiter_id(obj))
        return self.db.nodes.find({"policies.%s.object_related_list" % policy_id: {'$in': [unicode(obj['_id'])]}})

    def get_related_computers_of_emiters(self, obj, related_computers, related_objects):
        if self.walking_here(obj, related_objects):
            return related_computers
        object_related_list = self.get_object_related_list(obj)
        for object_related in object_related_list:
            self.get_related_computers(object_related, related_computers, related_objects)
        return related_computers

    def get_related_computers_of_user(self, obj, related_computers, related_objects):
        if self.walking_here(obj, related_objects):
            return related_computers
        return get_computer_of_user(self.db.nodes, obj, related_computers)

    def get_related_computers(self, obj, related_computers=None, related_objects=None):
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
        return obj != objold

    def get_object_ui(self, rule_type, obj, node, policy):
        if obj == {}:
            return {}
        if rule_type == 'save':
            if policy.get('is_emitter_policy', False):
                obj = self.db.nodes.find_one({'node_chef_id': node.name})
            return obj
        elif rule_type == 'policies':
            policy_id = unicode(policy['_id'])
            if policy.get('is_emitter_policy', False):
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

    def update_node_from_rules(self, rules, user, computer, obj_ui, obj, action, node, policy, rule_type, job_ids_by_computer):
        updated = updated_updated_by = False
        attributes_jobs_updated = []
        attributes_updated_by_updated = []
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
            if priority_obj.get('_id', None) == obj.get('_id', None) or action == DELETED_POLICY_ACTION:
                if callable(field_ui):
                    if is_user_policy(field_chef):
                        priority_obj = computer['user']
                    obj_ui_field = field_ui(priority_obj_ui, obj=priority_obj, node=node, field_chef=field_chef)
                else:
                    obj_ui_field = priority_obj_ui.get(field_ui, None)

                if obj_ui_field is None and action != DELETED_POLICY_ACTION:
                    continue
                elif obj_ui_field is None and action == DELETED_POLICY_ACTION:
                    try:
                        obj_ui_field = delete_dotted(node.attributes, field_chef)
                        updated = True
                    except KeyError:
                        pass
                else:
                    try:
                        value_field_chef = node.attributes.get_dotted(field_chef)
                    except KeyError:
                        value_field_chef = None
                    if obj_ui_field != value_field_chef:
                        node.attributes.set_dotted(field_chef, obj_ui_field)
                        updated = True
            if job_attr not in attributes_jobs_updated:
                if updated:
                    self.update_node_job_id(user, obj, action, computer, node, policy, job_attr, attributes_jobs_updated, job_ids_by_computer)
        return (node, (updated or updated_updated_by))

    def get_first_exists_node(self, ids, obj, action):
        for mongo_id in ids:
            node = self.db.nodes.find_one({'_id': ObjectId(mongo_id)})
            if node:
                if action != DELETED_POLICY_ACTION or unicode(obj.get('_id')) != mongo_id:
                    return node
        return {}

    def get_updated_by_fieldname(self, field_chef, policy, obj, computer):
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
        ou_ids = [ObjectId(ou_id) for ou_id in ou_ids]
        ous = [ou for ou in self.db.nodes.find({'_id': {'$in': ou_ids}})]
        ous.sort(key=lambda x: x['path'].count(','), reverse=True)
        return [unicode(ou['_id']) for ou in ous]

    def update_node_job_id(self, user, obj, action, computer, node, policy, attr, attributes_updated, job_ids_by_computer):
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
                                    administrator_username=user['username'])
        job_ids.append(unicode(job_id))
        job_ids_by_computer.append(job_id)
        attributes_updated.append(attr)
        node.attributes.set_dotted(attr, job_ids)

    def disassociate_object_from_group(self, obj):
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
        policies_apply = [(policy_id, action) for policy_id in obj[rule_type].keys()]
        if not objold:
            return policies_apply
        policies_delete = set(objold[rule_type].keys()) - set(obj[rule_type].keys())
        policies_delete = [(policy_id, DELETED_POLICY_ACTION) for policy_id in policies_delete]
        return policies_apply + policies_delete

    def update_node(self, user, computer, obj, objold, node, action, job_ids_by_computer, force_update):
        updated = False
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
                    node, updated_policy = self.update_node_from_rules(rules, user, computer, obj_ui, obj, action, node, policy, rule_type, job_ids_by_computer)
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
        schema = cookbook['metadata']['attributes']['json_schema']['object']
        validate(to_deep_dict(node.attributes), schema)

    def report_error(self, exception, job_ids, computer, prefix=None):
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
        message = 'No save in chef server. The node is not linked, it is possible that this node was imported from AD or LDAP'
        self.report_generic_error(user, obj, action, message, computer, status='warnings')

    def report_node_busy(self, computer, user, obj, action):
        message = 'No save in chef server. The node is busy'
        self.report_generic_error(user, obj, action, message, computer)

    def report_unknown_error(self, exception, user, obj, action, computer=None):
        message = 'No save in chef server. %s' % unicode(exception)
        self.report_generic_error(user, obj, action, message, computer)

    def report_generic_error(self, user, obj, action, message, computer=None, status='errors'):
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
        api = get_chef_api(self.app.conf, user)
        cookbook = get_cookbook(api, self.app.conf.get('chef.cookbook_name'))
        computers = computers or self.get_related_computers(obj)
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
                node, updated = self.update_node(user, computer, obj, objold, node, action, job_ids_by_computer, force_update)
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
        if are_new_jobs:
            invalidate_jobs(self.request, user)

    def object_created(self, user, objnew, computers=None):
        self.object_action(user, objnew, action='created', computers=computers)

    def object_changed(self, user, objnew, objold, computers=None):
        self.object_action(user, objnew, objold, action='changed', computers=computers)

    def object_deleted(self, user, obj, computers=None):
        obj_without_policies = deepcopy(obj)
        obj_without_policies['policies'] = {}
        object_changed = getattr(self, '%s_changed' % obj['type'])
        object_changed(user, obj_without_policies, obj, computers=computers)

    def object_moved(self, user, objnew, objold):
        api = get_chef_api(self.app.conf, user)
        try:
            func = globals()['apply_policies_to_%s' % objnew['type']]
        except KeyError:
            raise NotImplementedError
        func(self.db.nodes, objnew, user, api, initialize=True)

    def object_emiter_deleted(self, user, obj, computers=None):
        obj_id = unicode(obj['_id'])
        policy_id = unicode(self.get_policy_emiter_id(obj))
        object_related_list = self.get_object_related_list(obj)
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

    def group_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'Group', objnew)

    def group_moved(self, user, objnew, objold):
        self.log_action('moved', 'Storage', objnew)
        raise NotImplementedError

    def group_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.object_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Group', obj)

    def user_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'User', objnew)

    def user_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
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

    def computer_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'Computer', objnew)

    def computer_moved(self, user, objnew, objold):
        self.object_moved(user, objnew, objold)
        self.log_action('moved', 'Computer', objnew)

    def computer_deleted(self, user, obj, computers=None, direct_deleted=True):
        # 1 - Delete computer from chef server
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

    def ou_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'OU', objnew)

    def ou_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'OU', objnew)

    def ou_moved(self, user, objnew, objold):
        self.log_action('moved', 'OU', objnew)
        raise NotImplementedError

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
        self.log_action('deleted', 'OU', obj)

    def printer_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Printer', objnew)

    def printer_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'Printer', objnew)

    def printer_moved(self, user, objnew, objold):
        self.log_action('moved', 'Printer', objnew)
        raise NotImplementedError

    def printer_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.object_emiter_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Printer', obj)

    def storage_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Storage', objnew)

    def storage_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'Storage', objnew)

    def storage_moved(self, user, objnew, objold):
        self.log_action('moved', 'Storage', objnew)
        raise NotImplementedError

    def storage_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.object_emiter_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Storage', obj)

    def repository_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Storage', objnew)

    def repository_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'Storage', objnew)

    def repository_moved(self, user, objnew, objold):
        self.log_action('moved', 'Repository', objnew)
        raise NotImplementedError

    def repository_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.object_emiter_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Storage', obj)


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
def object_changed(user, objtype, objnew, objold, computers=None):
    self = object_changed
    func = getattr(self, '{0}_changed'.format(objtype), None)
    if func is not None:
        try:
            return func(user, objnew, objold, computers=computers)
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
