from copy import deepcopy

from bson import ObjectId

from chef import Node
from chef.node import NodeAttributes
from chef.exceptions import ChefError

from celery.task import Task, task
from celery.signals import task_prerun
from celery.exceptions import Ignore
from jsonschema import validate


from gecoscc.eventsmanager import JobStorage
from gecoscc.rules import get_rules, is_user_policy
from gecoscc.utils import (get_chef_api, create_chef_admin_user,
                           get_cookbook, get_filter_nodes_belonging_ou,
                           emiter_police_slug,
                           RESOURCES_RECEPTOR_TYPES, RESOURCES_EMITTERS_TYPES,
                           POLICY_EMITTER_SUBFIX)


class ChefTask(Task):
    abstract = True

    def __init__(self):
        self.db = self.app.conf.get('mongodb').get_database()
        self.init_jobid()
        self.logger = self.get_logger()

    def log(self, messagetype, message):
        assert messagetype in ('debug', 'info', 'warning', 'error', 'critical')
        op = getattr(self.logger, messagetype)
        op('[{0}] {1}'.format(self.jid, message))

    def init_jobid(self):
        if self.request is not None:
            self.jid = self.request.id
        else:
            self.jid = unicode(ObjectId())

    def walking_here(self, obj, related_objects):
        if related_objects is not None:
            if obj not in related_objects:
                related_objects.append(obj)
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
            if node not in related_objects:
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

    def get_related_computers_of_emiters(self, obj, related_computers, related_objects):
        if self.walking_here(obj, related_objects):
            return related_computers
        policy_id = unicode(self.db.policies.find_one({'slug': emiter_police_slug(obj['type'])})['_id'])
        object_related_list = self.db.nodes.find({"policies.%s.object_related_list" % policy_id: {'$in': [unicode(obj['_id'])]}})
        for object_related in object_related_list:
            self.get_related_computers(object_related, related_computers, related_objects)
        return related_computers

    def get_related_computers_of_user(self, obj, related_computers, related_objects):
        if self.walking_here(obj, related_objects):
            return related_computers
        user_computers = self.db.nodes.find({'_id': {'$in': obj['computers']}})
        for computer in user_computers:
            if computer not in related_computers:
                computer['user'] = obj
                related_computers.append(computer)
        return related_computers

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
        if objold is None:
            old_policies = {}
        else:
            old_policies = objold.get('policies', {})
        return new_policies != old_policies

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

    def update_node_from_rules(self, rules, user, computer, obj_ui, obj, action, node, policy, rule_type):
        updated = updated_updated_by = False
        attributes_jobs_updated = []
        attributes_updated_by_updated = []
        for field_chef, field_ui in rules.items():
            job_attr = '.'.join(field_chef.split('.')[:3]) + '.job_ids'
            updated_by_attr = self.get_updated_by_fieldname(field_chef, policy, obj, computer)
            priority_obj_ui = obj_ui
            obj_ui_field = None
            if (rule_type == 'policies' or not policy.get('is_emitter_policy', False)) and updated_by_attr not in attributes_updated_by_updated:
                updated_updated_by = updated_updated_by or self.update_node_updated_by(node, field_chef, obj, action, updated_by_attr, attributes_updated_by_updated)
            priority_obj = self.priority_object(node, updated_by_attr, obj, action)
            if priority_obj != obj:
                priority_obj_ui = self.get_object_ui(rule_type, priority_obj, node, policy)
            if priority_obj == obj or action == 'deleted':
                if callable(field_ui):
                    if is_user_policy(field_chef):
                        priority_obj = computer['user']
                    obj_ui_field = field_ui(priority_obj_ui, obj=priority_obj, node=node, field_chef=field_chef)
                else:
                    obj_ui_field = priority_obj_ui.get(field_ui, None)

                if obj_ui_field is None and action != 'deleted':
                    continue
                elif obj_ui_field is None and action == 'deleted':
                    try:
                        obj_ui_field = delete_dotted(node.attributes, field_chef)
                        updated = True
                    except KeyError:
                        pass
                elif obj_ui_field != node.attributes.get_dotted(field_chef):
                    node.attributes.set_dotted(field_chef, obj_ui_field)
                    updated = True
            if job_attr not in attributes_jobs_updated:
                if updated:
                    self.update_node_job_id(user, obj, action, node, job_attr, attributes_jobs_updated)
        return (node, (updated or updated_updated_by))

    def get_first_exists_node(self, ids, obj, action):
        for mongo_id in ids:
            node = self.db.nodes.find_one({'_id': ObjectId(mongo_id)})
            if node:
                if action != 'deleted' or unicode(obj.get('_id')) != mongo_id:
                    return node
        return {}

    def get_updated_by_fieldname(self, field_chef, policy, obj, computer):
        updated_path = '.'.join(field_chef.split('.')[:3])
        if is_user_policy(field_chef):
            if obj['type'] != 'user':
                user = computer['user']
            else:
                user = obj
            updated_path += '.users.' + user['name']
        updated_path += '.updated_by'
        return updated_path

    def priority_object(self, node, updated_by_fieldname, obj, action):
        if obj['type'] in ['computer', 'user'] and action != 'deleted':
            return obj
        try:
            updated_by = node.attributes.get_dotted(updated_by_fieldname).to_dict()
        except KeyError:
            updated_by = {}
        if not updated_by:
            if action == 'deleted':
                return {}
            else:
                return obj
        priority_object = {}

        if updated_by.get('computer', None):
            if action != 'deleted' or unicode(obj.get('_id')) != updated_by['computer']:
                priority_object = self.db.nodes.find_one({'_id': ObjectId(updated_by['computer'])})
        if not priority_object and updated_by.get('user', None):
            if action != 'deleted' or unicode(obj.get('_id')) != updated_by['user']:
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
            if action == 'deleted':
                del updated_by[obj_type]
            else:
                updated_by[obj_type] = obj_id
            updated = True
        else:  # Ous or groups
            updated_by_type = updated_by.get(obj_type, [])
            if action == 'deleted':
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
            # TODO: Remove it when the users attr is a dictionary
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

    def update_node_job_id(self, user, obj, action, node, attr, attributes_updated):
        if node.attributes.has_dotted(attr):
            job_ids = node.attributes.get_dotted(attr)
        else:
            job_ids = []
        job_storage = JobStorage(self.db.jobs, user)
        job_status = 'processing'
        job_id = job_storage.create(objid=obj['_id'], type=obj['type'], op=action, status=job_status)
        job_ids.append(unicode(job_id))
        attributes_updated.append(attr)
        node.attributes.set_dotted(attr, job_ids)

    def get_policies(self, rule_type, action, obj, objold):
        policies_add = [(policy_id, action) for policy_id in obj[rule_type].keys()]
        if not objold:
            return policies_add
        policies_delete = set(objold[rule_type].keys()) - set(obj[rule_type].keys())
        policies_delete = [(policy_id, 'deleted') for policy_id in policies_delete]
        return policies_add + policies_delete

    def update_node(self, user, computer, obj, objold, node, action):
        updated = False
        if action == 'deleted':
            return (None, False)
        elif action in ['changed', 'created']:
            if obj['type'] in RESOURCES_RECEPTOR_TYPES:  # ou, user, comp, group
                if self.is_updating_policies(obj, objold):
                    rule_type = 'policies'
                    for policy_id, action in self.get_policies(rule_type, action, obj, objold):
                        policy = self.db.policies.find_one({"_id": ObjectId(policy_id)})
                        if action == 'deleted':
                            rules, obj_ui = self.get_rules_and_object(rule_type, objold, node, policy)
                        else:
                            rules, obj_ui = self.get_rules_and_object(rule_type, obj, node, policy)
                        node, updated_policy = self.update_node_from_rules(rules, user, computer, obj_ui, obj, action, node, policy, rule_type)
                        if not updated and updated_policy:
                            updated = True
                return (node, updated)
            elif obj['type'] in RESOURCES_EMITTERS_TYPES:  # printer, storage, repository
                rule_type = 'save'
                if self.is_updated_node(obj, objold):
                    policy = self.db.policies.find_one({'slug': emiter_police_slug(obj['type'])})
                    rules, obj_receptor = self.get_rules_and_object(rule_type, obj, node, policy)
                    node, updated = self.update_node_from_rules(rules, user, computer, obj, obj_receptor, action, node, policy, rule_type)
                return (node, updated)
        raise ValueError('The action should be deleted, changed or created')

    def validate_data(self, node, cookbook, api):
        schema = cookbook['metadata']['attributes']['json_schema']['object']
        validate(to_deep_dict(node.attributes), schema)

    def object_action(self, user, obj, objold=None, action=None, computers=None):
        api = get_chef_api(self.app.conf, user)
        cookbook = get_cookbook(api, self.app.conf.get('chef.cookbook_name'))
        computers = computers or self.get_related_computers(obj)
        for computer in computers:
            try:
                node_chef_id = computer.get('node_chef_id', None)
                node = Node(node_chef_id, api)
                if obj['type'] == 'computer' and action == 'deleted':
                    node.delete()
                else:
                    node, updated = self.update_node(user, computer, obj, objold, node, action)
                    if not updated:
                        continue
                    # TODO: Uncomment it when the users attr is a dictionary
                    #self.validate_data(node, cookbook, api)
                    node.save()
            except Exception as e:
                # TODO Report this error
                print e

    def object_created(self, user, objnew, computers=None):
        self.object_action(user, objnew, action='created', computers=computers)

    def object_changed(self, user, objnew, objold, computers=None):
        self.object_action(user, objnew, objold, action='changed', computers=computers)

    def object_deleted(self, user, obj, computers=None):
        self.object_action(user, obj, action='deleted', computers=computers)

    def log_action(self, log_action, resource_name, objnew):
        self.log('info', '{0} {1} {2}'.format(resource_name, log_action, objnew['_id']))

    def group_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Group', objnew)

    def group_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'Group', objnew)

    def group_deleted(self, user, obj, computers=None):
        self.object_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Group', obj)

    def user_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'User', objnew)

    def user_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'User', objnew)

    def user_deleted(self, user, obj, computers=None):
        self.object_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'User', obj)

    def computer_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Computer', objnew)

    def computer_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'Computer', objnew)

    def computer_deleted(self, user, obj, computers=None):
        self.object_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Computer', obj)

    def ou_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'OU', objnew)

    def ou_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'OU', objnew)

    def ou_deleted(self, user, obj, computers=None):
        self.object_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'OU', obj)

    def printer_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Printer', objnew)

    def printer_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'Printer', objnew)

    def printer_deleted(self, user, obj, computers=None):
        self.object_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Printer', obj)

    def storage_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Storage', objnew)

    def storage_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'Storage', objnew)

    def storage_deleted(self, user, obj, computers=None):
        self.object_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Storage', obj)

    def repository_created(self, user, objnew, computers=None):
        self.object_created(user, objnew, computers=computers)
        self.log_action('created', 'Storage', objnew)

    def repository_changed(self, user, objnew, objold, computers=None):
        self.object_changed(user, objnew, objold, computers=computers)
        self.log_action('changed', 'Storage', objnew)

    def repository_deleted(self, user, obj, computers=None):
        self.object_deleted(user, obj, computers=computers)
        self.log_action('deleted', 'Storage', obj)

    def adminuser_created(self, user, objnew, computers=None):
        api = get_chef_api(self.app.conf, user)
        create_chef_admin_user(api, self.app.conf, objnew['username'], objnew['plain_password'])
        self.log_action('created', 'AdminUser', objnew)


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
        return func(user, obj, computers=computers)

    else:
        self.log('error', 'The method {0}_created does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_changed(user, objtype, objnew, objold, computers=None):
    self = object_changed
    func = getattr(self, '{0}_changed'.format(objtype), None)
    if func is not None:
        return func(user, objnew, objold, computers=computers)

    else:
        self.log('error', 'The method {0}_changed does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_deleted(user, objtype, obj, computers=None):
    self = object_changed

    func = getattr(self, '{0}_deleted'.format(objtype), None)
    if func is not None:
        return func(user, obj, computers=computers)

    else:
        self.log('error', 'The method {0}_deleted does not exist'.format(
            objtype))

# Utils to NodeAttributes chef class


def to_deep_dict(node_attr):
    merged = {}
    for d in reversed(node_attr.search_path):
        merged = dict_merge(merged, d)
    return merged


def dict_merge(a, b):
    '''recursively merges dict's. not just simple a['key'] = b['key'], if
    both a and bhave a key who's value is a dict then dict_merge is called
    on both values and the result stored in the returned dictionary.'''
    if not isinstance(b, dict):
        return b
    result = deepcopy(a)
    for k, v in b.iteritems():
        if k in result and isinstance(result[k], dict):
                result[k] = dict_merge(result[k], v)
        else:
            result[k] = deepcopy(v)
    return result


def delete_dotted(dest, key):
    """Set an attribute using a dotted key path. See :meth:`.get_dotted`
    for more information on dotted paths.

    Example::

        node.attributes.set_dotted('apache.log_dir', '/srv/log')
    """
    keys = key.split('.')
    last_key = keys.pop()
    for k in keys:
        if k not in dest:
            dest[k] = {}
        dest = dest[k]
        if not isinstance(dest, NodeAttributes):
            raise ChefError
    del dest[last_key]