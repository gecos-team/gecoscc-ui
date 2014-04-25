import os
from copy import deepcopy

from bson import ObjectId
from celery.task import Task, task
from celery.signals import task_prerun
from celery.exceptions import Ignore
from chef import Node, ChefAPI
from chef.exceptions import ChefError
from jsonschema import validate

from gecoscc.eventsmanager import JobStorage
from gecoscc.rules import RULES_NODE
from gecoscc.utils import get_pem_for_username


RESOURCES_RECEPTOR_TYPES = ('computer', 'ou', 'user', 'group')
RESOURCES_EMITTERS_TYPES = ('printer', 'storage', 'repository')


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

    def get_related_computers_of_computer(self, obj, related_computers, related_objects):
        if related_objects is not None:
            if obj not in related_objects:
                related_objects.append(obj)
            else:
                return related_computers
        related_computers.append(obj)
        return related_computers

    def get_related_computers_of_group(self, obj, related_computers, related_objects):
        if obj not in related_objects:
            related_objects.append(obj)
        else:
            return related_computers
        for node_id in obj['members']:
            node = self.db.nodes.find_one({'_id': node_id})
            if node not in related_objects:
                self.get_related_computers(node, related_computers, related_objects)
        return related_computers

    def get_related_computers_of_ou(self, ou, related_computers, related_objects):
        if related_objects is not None:
            if ou not in related_objects:
                related_objects.append(ou)
            else:
                return related_computers
        computers = self.db.nodes.find({'path': {'$regex': '.*,%s.*' % ou['_id']},
                                        'type': 'computer'})
        for computer in computers:
            self.get_related_computers_of_computer(computer,
                                                   related_computers,
                                                   related_objects)
        return related_computers

    def get_related_computers_of_emiters(self, obj, related_computers, related_objects):
        if related_objects is not None:
            if obj not in related_objects:
                related_objects.append(obj)
            else:
                return related_computers
        raise NotImplementedError

    def get_related_computers_of_user(self, obj, related_computers, related_objects):
        if related_objects is not None:
            if obj not in related_objects:
                related_objects.append(obj)
            else:
                return related_computers
        raise NotImplementedError

    def get_related_computers(self, obj, related_computers=None, related_objects=None):
        if related_objects is None and obj['type'] == 'group':
            related_objects = []

        if related_computers is None:
            related_computers = []

        obj_type = obj['type']

        if obj['type'] in RESOURCES_EMITTERS_TYPES:
            obj_type = 'emiters'
        get_realted_computers_of_type = getattr(self, 'get_related_computers_of_%s' % obj_type)
        return get_realted_computers_of_type(obj, related_computers, related_objects)

    def get_related_cookbook(self, api):
        cookbook_name = self.app.conf.get('chef.cookbook_name')
        cookbook = api['/cookbooks/' + cookbook_name]
        cookbook[cookbook_name]['versions'].sort(key=lambda s: map(int, s['version'].split('.')),
                                                 reverse=True)
        last_cookbook = cookbook[cookbook_name]['versions'][0]
        return api['/cookbooks/%s/%s' % (cookbook_name,
                                         last_cookbook['version'])]

    def is_adding_policy(self, obj, objold):
        new_policies = obj.get('policies', None)
        old_policies = objold.get('policies', None)
        return new_policies != old_policies

    def get_rules(self, rule_type, obj, policy_id=None):
        if rule_type == 'save':
            return (RULES_NODE[obj['type']][rule_type], obj)
        elif rule_type == 'policy':
            policy = self.db.policies.find_one({"_id": ObjectId(policy_id)})
            return (RULES_NODE[obj['type']]['policies'][policy['slug']],
                    obj['policies'][policy_id])
        return ValueError("The rule type should be save or policy")

    def update_node_from_rules(self, rules, user, computer, obj_ui, obj, action, node):
        updated = False
        attributes_updated = []
        for field_chef, field_ui in rules.items():
            if obj_ui.get(field_ui, None) is None:
                continue
            elif obj_ui.get(field_ui, None) == node.attributes.get_dotted(field_chef):
                continue
            elif obj['type'] != 'computer':
                try:
                    node.default.get_dotted(field_chef)
                    continue
                except KeyError:
                    pass
            node.attributes.set_dotted(field_chef, obj_ui[field_ui])
            updated = True
            attr = '.'.join(field_chef.split('.')[:3]) + '.job_ids'
            if attr not in attributes_updated:
                self.update_node_job_id(user, obj, action, node, attr, attributes_updated)
        return (node, updated)

    def update_node_job_id(self, user, obj, action, node, attr, attributes_updated):
        if node.attributes.has_dotted(attr):
            job_ids = node.attributes.get_dotted(attr)
        else:
            job_ids = []
        job_storage = JobStorage(self.db.jobs, user)
        job_status = 'processing'
        job_id = job_storage.create(objid=obj['_id'], type=obj['type'], op=action, status=job_status)
        job_ids.append({'id': unicode(job_id), 'status': job_status})
        attributes_updated.append(attr)
        node.attributes.set_dotted(attr, job_ids)

    def update_node(self, user, computer, obj, objold, node, action):
        updated = False
        if action == 'deleted':
            return (None, False)
        elif action in ['changed', 'created']:
            if obj['type'] in RESOURCES_RECEPTOR_TYPES:  # ou, user, comp, group
                if self.is_adding_policy(obj, objold):
                    rule_type = 'policy'
                    for policy_id in obj['policies'].keys():
                        rules, obj_ui = self.get_rules(rule_type, obj, policy_id)
                        node, updated_policy = self.update_node_from_rules(rules, user, computer, obj_ui, obj, action, node)
                        if not updated and updated_policy:
                            updated = True
                return (node, updated)
            else:  # printer, storage, repo
                rule_type = 'save'
                rules, obj = self.get_rules(rule_type, obj)
                return self.update_node_from_rules(rules, user, computer, obj_ui, obj, action, node)
        raise ValueError('The action should be deleted, changed or created')

    def validate_data(self, node, cookbook, api):
        schema = cookbook['metadata']['attributes']['json_schema']['object']
        validate(to_deep_dict(node.attributes), schema)

    def get_api(self, user=None):
        username = user['username']
        url = user.get('variables', {}).get('chef_server_uri', None) or self.app.conf.get('chef.url')
        chef_pem = get_pem_for_username(self.app.conf, user['username'])
        if not os.path.exists(chef_pem):
            raise ChefError('User has no pem to access chef server')
        api = ChefAPI(url, chef_pem, username)
        return api

    def object_action(self, user, obj, objold=None, action=None):
        api = self.get_api(user)
        cookbook = self.get_related_cookbook(api)
        computers = self.get_related_computers(obj)
        for computer in computers:
            hardcode_computer_name = 'gecos-workstation-1'
            node = Node(hardcode_computer_name, api)
            node, updated = self.update_node(user, computer, obj, objold, node, action)
            if not updated:
                continue
            self.validate_data(node, cookbook, api)
            node.save()

    def object_created(self, user, objnew):
        self.object_action(user, objnew, action='created')

    def object_changed(self, user, objnew, objold):
        self.object_action(user, objnew, objold, action='changed')

    def object_deleted(self, user, obj):
        self.object_action(user, obj, action='deleted')

    def log_action(self, log_action, resource_name, objnew):
        self.log('info', '{0} {1} {2}'.format(resource_name, log_action, objnew['_id']))

    def group_created(self, user, objnew):
        self.object_created(user, objnew)
        self.log_action('created', 'Group', objnew)

    def group_changed(self, user, objnew, objold):
        self.object_changed(user, objnew, objold)
        self.log_action('changed', 'Group', objnew)

    def group_deleted(self, user, obj):
        self.object_deleted(user, obj)
        self.log_action('deleted', 'Group', obj)

    def user_created(self, user, objnew):
        self.object_created(user, objnew)
        self.log_action('created', 'User', objnew)

    def user_changed(self, user, objnew, objold):
        self.object_changed(user, objnew, objold)
        self.log_action('changed', 'User', objnew)

    def user_deleted(self, user, obj):
        self.object_deleted(user, obj)
        self.log_action('deleted', 'User', obj)

    def computer_created(self, user, objnew):
        self.object_created(user, objnew)
        self.log_action('created', 'Computer', objnew)

    def computer_changed(self, user, objnew, objold):
        self.object_changed(user, objnew, objold)
        self.log_action('changed', 'Computer', objnew)

    def computer_deleted(self, user, obj):
        self.object_deleted(user, obj)
        self.log_action('deleted', 'Computer', obj)

    def ou_created(self, user, objnew):
        self.object_created(user, objnew)
        self.log_action('created', 'OU', objnew)

    def ou_changed(self, user, objnew, objold):
        self.object_changed(user, objnew, objold)
        self.log_action('changed', 'OU', objnew)

    def ou_deleted(self, user, obj):
        self.object_deleted(user, obj)
        self.log_action('deleted', 'OU', obj)

    def printer_created(self, user, objnew):
        self.object_created(user, objnew)
        self.log_action('created', 'Printer', objnew)

    def printer_changed(self, user, objnew, objold):
        self.object_changed(user, objnew, objold)
        self.log_action('changed', 'Printer', objnew)

    def printer_deleted(self, user, obj):
        self.object_deleted(user, obj)
        self.log_action('deleted', 'Printer', obj)

    def storage_created(self, user, objnew):
        self.object_created(user, objnew)
        self.log_action('created', 'Storage', objnew)

    def storage_changed(self, user, objnew, objold):
        self.object_changed(user, objnew, objold)
        self.log_action('changed', 'Storage', objnew)

    def storage_deleted(self, user, obj):
        self.object_deleted(user, obj)
        self.log_action('deleted', 'Storage', obj)

    def adminuser_created(self, user, objnew):
        api = self.get_api(user)
        data = {'name': objnew['username'], 'password': objnew['plain_password'], 'admin': True}
        chef_user = api.api_request('POST', '/users', data=data)
        private_key = chef_user.get('private_key', None)
        if private_key:
            fileout = open(self.get_pem_for_username(objnew['username']), 'w')
            fileout.write(private_key)
            fileout.close()
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
def object_created(user, objtype, obj):
    self = object_created

    func = getattr(self, '{0}_created'.format(objtype), None)
    if func is not None:
        return func(user, obj)

    else:
        self.log('error', 'The method {0}_created does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_changed(user, objtype, objnew, objold):
    self = object_changed
    func = getattr(self, '{0}_changed'.format(objtype), None)
    if func is not None:
        return func(user, objnew, objold)

    else:
        self.log('error', 'The method {0}_changed does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_deleted(user, objtype, obj):
    self = object_changed

    func = getattr(self, '{0}_deleted'.format(objtype), None)
    if func is not None:
        return func(user, obj)

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
