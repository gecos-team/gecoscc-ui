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
import json
import os
import pytz
import random
import string
import time
import re
import pkg_resources
import logging

from bson import ObjectId, json_util
from copy import deepcopy, copy

from chef import ChefAPI, Client
from chef import Node as ChefNode
from chef.exceptions import ChefError
from chef.node import NodeAttributes

from pyramid.threadlocal import get_current_registry

from collections import defaultdict

RESOURCES_RECEPTOR_TYPES = ('computer', 'ou', 'user', 'group')
RESOURCES_EMITTERS_TYPES = ('printer', 'storage', 'repository')
POLICY_EMITTER_SUBFIX = '_can_view'
USER_MGMT = 'users_mgmt'
SOURCE_DEFAULT = MASTER_DEFAULT = 'gecos'
USE_NODE = 'use_node'

logger = logging.getLogger(__name__)

def get_policy_emiter_id(collection, obj):
    '''
    Get the id from a emitter policy
    '''
    return collection.policies.find_one({'slug': emiter_police_slug(obj['type'])})['_id']


def get_object_related_list(collection, obj):
    '''
    Get the objects related list to an object
    '''
    policy_id = unicode(get_policy_emiter_id(collection, obj))
    return collection.nodes.find({"policies.%s.object_related_list" % policy_id: {'$in': [unicode(obj['_id'])]}})


def merge_lists(collection, obj, old_obj, attribute, remote_attribute, keyname='_id'):
    """
        Merge a list of relations in a two ways relation model.
    """

    newmembers = obj.get(attribute, [])
    oldmembers = old_obj.get(attribute, [])

    adds = [n for n in newmembers if n not in oldmembers]
    removes = [n for n in oldmembers if n not in newmembers]

    for group_id in removes:
        collection.update({
            keyname: group_id
        }, {
            '$pull': {
                remote_attribute: obj[keyname]
            }
        }, multi=False)

    for group_id in adds:

        # Add newmember to new group
        collection.update({
            keyname: group_id
        }, {
            '$push': {
                remote_attribute: obj[keyname]
            }
        }, multi=False)

# mongo utils


def get_computer_of_user(collection_nodes, user, related_computers=None):
    if related_computers is None:
        related_computers = []
    user_computers = collection_nodes.find({'_id': {'$in': user['computers']}})
    for computer in user_computers:
        if computer not in related_computers:
            computer['user'] = user
            related_computers.append(computer)
        elif 'user' not in computer:
            computer_index = related_computers.index(computer)
            related_computers[computer_index]['user'] = user
    return related_computers


def get_filter_ous_from_path(path):
    ou_ids = [ObjectId(ou_id) for ou_id in path.split(',') if ou_id != 'root']
    return {'_id': {'$in': ou_ids}}


def get_filter_nodes_parents_ou(db, ou_id, item_id):
    item = db.nodes.find_one({'_id': ObjectId(item_id)})
    if item['type'] == 'ou':
        ou = item
        ou_id = ou['_id']
    else:
        ou = db.nodes.find_one({'_id': ObjectId(ou_id)})
    ou_path = ou['path']
    filters = {'$regex': '%s,%s$' % (ou_path, ou_id)}
    path_split = ou_path.split(',')
    for path_step in path_split:
        filters['$regex'] += '|%s$' % path_step
    return filters


def get_filter_nodes_belonging_ou(ou_id):
    if ou_id == 'root':
        return {'$regex': '%s.*' % ou_id}
    return {'$regex': '.*,%s.*' % ou_id}


def get_filter_children_ou(ou_id, next_level=True):
    if ou_id == 'root':
        return ou_id
    regex = '.*,%s' % ou_id
    if next_level:
        regex = '%s$' % regex
    return {'$regex': regex}


def get_items_ou_children(ou_id, collection_nodes, objtype=None, filters=None, next_level=True):
    filters = filters or {}
    if objtype:
        filters['type'] = objtype
    if ou_id:
        filters['path'] = get_filter_children_ou(ou_id, next_level=next_level)
    else:
        filters['path'] = 'no-root'
    ous = collection_nodes.find(filters).sort('name')
    return [{'_id': unicode(ou['_id']),
             'name': ou['name']} for ou in ous]


def emiter_police_slug(emiter_type):
    return '%s%s' % (emiter_type, POLICY_EMITTER_SUBFIX)


def oids_filter(request):
    oids = request.GET.get('oids')
    return {
        '$or': [{'_id': ObjectId(oid)} for oid in oids.split(',')]
    }

# Chef utils


def password_generator(size=8, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for x in range(size))


def get_chef_api(settings, user):
    username = toChefUsername(user['username'])
    chef_url = settings.get('chef.url')
    chef_user_pem = get_pem_path_for_username(settings, username, 'chef_user.pem')
    api = _get_chef_api(chef_url, username, chef_user_pem, settings.get('chef.ssl.verify'), settings.get('chef.version'))

    return api


def _get_chef_api(chef_url, username, chef_pem, chef_ssl_verify, chef_version = '11.0.0'):
    if not os.path.exists(chef_pem):
        raise ChefError('User has no pem to access chef server')
    if chef_ssl_verify == 'False' or chef_ssl_verify == 'True':
        chef_ssl_verify = bool(chef_ssl_verify)

    api = ChefAPI(chef_url, chef_pem, username, chef_version, ssl_verify = False)

    return api


def create_chef_admin_user(api, settings, usrname, password=None, email='nobody@nobody.es'):
    username = toChefUsername(usrname)
    if password is None:
        password = password_generator()
        
    if api.version_parsed >= pkg_resources.parse_version("12.0.0"):
        # Chef 12 user data
        data = {'name': username, 'password': password, 'admin': True, 'display_name': username, 'email': email}
    else:
        # Chef 11 user data
        data = {'name': username, 'password': password, 'admin': True}
        
    chef_user = api.api_request('POST', '/users', data=data)

    user_private_key = chef_user.get('private_key', None)
    if user_private_key:
        save_pem_for_username(settings, username, 'chef_user.pem', user_private_key)

    chef_client = Client.create(name=username, api=api, admin=True)
    client_private_key = getattr(chef_client, 'private_key', None)
    if client_private_key:
        save_pem_for_username(settings, username, 'chef_client.pem', client_private_key)


def delete_chef_admin_user(api, settings, usrname):
    username = toChefUsername(usrname)
    try:
        api.api_request('DELETE', '/users/%s/' % username)
        api.api_request('DELETE', '/clients/%s/' % username)
        return True
    except:
        return False


def remove_chef_computer_data(computer, api, policies=None):
    '''
    Remove computer policies in chef node
    '''
    node_chef_id = computer.get('node_chef_id', None)
    if node_chef_id:
        node = reserve_node_or_raise(node_chef_id, api, 'gcc-remove-computer-data-%s' % random.random())
        if node:
            settings = get_current_registry().settings
            cookbook_name = settings.get('chef.cookbook_name')
            cookbook = node.normal.get(cookbook_name)
            if policies:
                for policy in policies:
                    policy_path = policy[1]
                    policy_field = policy[2]
                    try:
                        cookbook[policy_path].pop(policy_field)
                    except KeyError:
                        continue
            else:
                for mgmt in cookbook.keys():
                    if mgmt == USER_MGMT:
                        continue
                    cookbook.pop(mgmt)
            save_node_and_free(node)


def remove_chef_user_data(user, computers, api, policy_fields=None):
    '''
    Remove computer policies in chef node
    '''
    settings = get_current_registry().settings
    cookbook_name = settings.get('chef.cookbook_name')
    for computer in computers:
        node_chef_id = computer.get('node_chef_id', None)
        if node_chef_id:
            node = reserve_node_or_raise(node_chef_id, api, 'gcc-remove-user-data-%s' % random.random())
            if node:
                if policy_fields:
                    for policy in policy_fields:
                        try:
                            user_mgmt = node.normal.get_dotted('%s.%s' % (cookbook_name + '.' + USER_MGMT, policy))
                            users = user_mgmt.get('users')
                            if not users:
                                continue
                            users.pop(user['name'])
                            save_node_and_free(node)
                        except KeyError:
                            save_node_and_free(node)
                else:
                    try:
                        user_mgmt = node.normal.get_dotted('%s.%s' % (cookbook_name, USER_MGMT))
                        for policy in user_mgmt:
                            try:
                                users = user_mgmt.get(policy).get('users')
                                if not users:
                                    continue
                                users.pop(user['name'])
                            except KeyError:
                                continue
                        save_node_and_free(node)
                    except KeyError:
                        save_node_and_free(node)


def reserve_node_or_raise(node_id, api, controller_requestor='gcc', attempts=1):
    node, is_busy = is_node_busy_and_reserve_it(node_id, api, controller_requestor, attempts)
    if is_busy:
        raise NodeBusyException("Node %s is busy" % node_id)
    return node


def is_node_busy_and_reserve_it(node_id, api, controller_requestor='gcc', attempts=1):
    is_busy = True
    for attempt in range(attempts):
        node, is_busy = _is_node_busy_and_reserve_it(node_id, api, controller_requestor)
        if not is_busy:
            break
        settings = get_current_registry().settings
        seconds_sleep_is_busy = settings.get('chef.seconds_sleep_is_busy')
        time.sleep(int(seconds_sleep_is_busy))
    return (node, is_busy)


def _is_node_busy_and_reserve_it(node_id, api, controller_requestor='gcc'):
    '''
    Check if the node is busy, else try to get it and write in control and expiration date in the field USE_NODE.
    '''
    settings = get_current_registry().settings
    seconds_block_is_busy = int(settings.get('chef.seconds_block_is_busy'))
    time_to_exp = datetime.timedelta(seconds=seconds_block_is_busy)

    time_get = time.time()
    node = ChefNode(node_id, api)
    time_get = time.time() - time_get

    current_use_node = node.attributes.get(USE_NODE, {})
    current_use_node_control = current_use_node.get('control', None)
    current_use_node_exp_date = current_use_node.get('exp_date', None)
    if current_use_node_exp_date:
        current_use_node_exp_date = json.loads(current_use_node_exp_date, object_hook=json_util.object_hook)
        current_use_node_exp_date = current_use_node_exp_date.astimezone(pytz.utc).replace(tzinfo=None)
        now = datetime.datetime.now()
        if now - current_use_node_exp_date > time_to_exp:
            current_use_node_control = None
    if current_use_node_control == controller_requestor:
        return (node, False)
    elif current_use_node_control is None:
        exp_date = datetime.datetime.utcnow() + time_to_exp
        node.attributes.set_dotted(USE_NODE, {'control': controller_requestor,
                                              'exp_date': json.dumps(exp_date, default=json_util.default)})
        node.save()

        smart_lock_sleep_parameter = settings.get('chef.smart_lock_sleep_factor', 3)
        seconds_sleep_is_busy = time_get * int(smart_lock_sleep_parameter)
        time.sleep(seconds_sleep_is_busy)

        node2 = ChefNode(node.name, api)  # second check
        current_use_node2 = node2.attributes.get(USE_NODE, {})
        current_use_control2 = current_use_node2.get('control', None)
        if current_use_control2 == controller_requestor:
            return (node2, False)
    return (node, True)


def save_node_and_free(node, api=None, refresh=False):
    if refresh and api:
        node = ChefNode(node.name, api)
    node.attributes.set_dotted(USE_NODE, {})
    node.save()


class NodeBusyException(Exception):
    pass


class NodeNotLinked(Exception):
    pass

# Utils to NodeAttributes chef class

def recursive_defaultdict():
    return defaultdict(recursive_defaultdict)

def setpath(d, p, k):
    if len(p) == 1:
        d[p[0]] = k
    else:
        setpath(d[p[0]], p[1:], k)

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


# Visibility utils

def is_visible_group(db, group_id, node, ou_id=None):
    ou_id = ou_id or node['path'].split(',')[-1]
    return db.nodes.find_one({'_id': group_id,
                              'path': get_filter_nodes_parents_ou(db,
                                                                  ou_id,
                                                                  node['_id'])})


def visibility_group(db, obj):
    groups = obj['memberof']
    visible_groups = []
    hide_groups = []
    ou_id = obj['path'].split(',')[-1]
    for group_id in groups:
        is_visible = is_visible_group(db, group_id, obj, ou_id)
        if is_visible:
            visible_groups.append(group_id)
        else:
            hide_groups.append(group_id)
    if visible_groups != groups:
        db.nodes.update({'_id': obj['_id']},
                        {'$set': {'memberof': visible_groups}})
        for hide_group_id in hide_groups:
            group = db.nodes.find_one({'_id': hide_group_id})
            members = list(set(group['members']))
            try:
                del members[members.index(obj['_id'])]
            except ValueError:
                pass
            db.nodes.update({'_id': hide_group_id},
                            {'$set': {'members': members}})
        return db.nodes.find_one({'_id': obj['_id']})
    return obj


def visibility_object_related(db, obj):
    from gecoscc.tasks import SOFTWARE_PROFILE_SLUG
    policies = obj.get('policies', None)
    if not policies:
        return obj
    emitter_policies = db.policies.find({'is_emitter_policy': True})
    obj_id = obj['_id']
    ou_id = obj['path'].split(',')[-1]
    have_updated = False
    for emitter_policy in emitter_policies:
        emitter_policy_id = emitter_policy['_id']
        if unicode(emitter_policy_id) in obj['policies']:
            object_related_list = obj['policies'][unicode(emitter_policy_id)].get('object_related_list', [])
            object_related_visible = []
            for object_related_id in object_related_list:
                if emitter_policy['slug'] == SOFTWARE_PROFILE_SLUG:
                    is_visible = db.software_profiles.find_one({
                                                               '_id': ObjectId(object_related_id)
                                                               })
                else:
                    is_visible = is_object_visible(db.nodes, object_related_id, ou_id, obj_id)
                if is_visible:
                    object_related_visible.append(object_related_id)
            if object_related_list != object_related_visible:
                if object_related_visible:
                    policies[unicode(emitter_policy_id)]['object_related_list'] = object_related_visible
                else:
                    del policies[unicode(emitter_policy_id)]
                have_updated = True
    if have_updated:
        obj = update_collection_and_get_obj(db.nodes, obj_id, policies)
    return obj


def get_job_errors_from_computer(jobs_collection, computer):
    return jobs_collection.find({'computerid': computer['_id'],
                                 '$or': [{'status': 'warnings'}, {'status': 'errors'}]})


def recalc_node_policies(nodes_collection, jobs_collection, computer, auth_user, cookbook_name,
                         api=None, initialize=True, use_celery=False):
    job_errors = get_job_errors_from_computer(jobs_collection, computer).count()
    node_chef_id = computer.get('node_chef_id', None)
    if not node_chef_id:
        return (False, 'The computer %s does not have node_chef_id' % computer['name'])

    node = ChefNode(node_chef_id, api)
    if not node.exists:
        return (False, 'Node %s does not exists in chef server' % node_chef_id)

    is_inizialized = node.attributes.get(cookbook_name)
    if not is_inizialized:
        return (False, 'Node %s is not inizialized in chef server' % node_chef_id)

    apply_policies_to_computer(nodes_collection, computer, auth_user, api,
                               initialize=initialize,
                               use_celery=use_celery)
    users = nodes_collection.find({'type': 'user', 'computers': computer['_id']})
    for user in users:
        apply_policies_to_user(nodes_collection, user, auth_user, api,
                               initialize=initialize,
                               use_celery=use_celery)
    new_job_errors = get_job_errors_from_computer(jobs_collection, computer).count()
    if new_job_errors > job_errors:
        return (False, 'The computer %s had problems while it was updating' % computer['name'])
    return (True, 'success')


def is_object_visible(nodes_collection, object_related_id, ou_id, obj_id):
    return nodes_collection.find_one({'_id': ObjectId(object_related_id),
                                      'path': get_filter_nodes_parents_ou(nodes_collection.database,
                                                                          ou_id,
                                                                          obj_id)})


def update_collection_and_get_obj(nodes_collection, obj_id, policies_value):
    '''
    Updates the node policy and return the obj
    '''
    nodes_collection.update({'_id': obj_id}, {'$set': {'policies': policies_value}})
    return nodes_collection.find_one({'_id': obj_id})


def apply_policies_to_computer(nodes_collection, computer, auth_user, api=None, initialize=False, use_celery=True, policies_collection=None):
    from gecoscc.tasks import object_changed, object_created
    if use_celery:
        object_created = object_created.delay
        object_changed = object_changed.delay

    if api and initialize:
        computer = visibility_group(nodes_collection.database, computer)
        computer = visibility_object_related(nodes_collection.database, computer)
        remove_chef_computer_data(computer, api)

    ous = nodes_collection.find(get_filter_ous_from_path(computer['path']))
    for ou in ous:
        if ou.get('policies', {}):
            object_changed(auth_user, 'ou', ou, {}, computers=[computer])

    groups = nodes_collection.find({'_id': {'$in': computer.get('memberof', [])}})
    for group in groups:
        if group.get('policies', {}):
            object_changed(auth_user, 'group', group, {}, computers=[computer])

    object_created(auth_user, 'computer', computer, computers=[computer])


def apply_policies_to_user(nodes_collection, user, auth_user, api=None, initialize=False, use_celery=True, policies_collection=None):
    from gecoscc.tasks import object_changed, object_created
    if use_celery:
        object_created = object_created.delay
        object_changed = object_changed.delay

    computers = get_computer_of_user(nodes_collection, user)

    if api and initialize:
        user = visibility_group(nodes_collection.database, user)
        user = visibility_object_related(nodes_collection.database, user)
        remove_chef_user_data(user, computers, api)

    if not computers:
        return

    ous = nodes_collection.find(get_filter_ous_from_path(user['path']))
    for ou in ous:
        if ou.get('policies', {}):
            object_changed(auth_user, 'ou', ou, {}, computers=computers)

    groups = nodes_collection.find({'_id': {'$in': user.get('memberof', [])}})
    for group in groups:
        if group.get('policies', {}):
            object_changed(auth_user, 'group', group, {}, computers=computers)

    object_created(auth_user, 'user', user, computers=computers)


def apply_policies_to_emitter_object(nodes_collection, obj, auth_user, slug, api=None, initialize=False, use_celery=True, policies_collection=None):
    '''
    Checks if a emitter object is within the scope of the objects that is related and then update policies
    '''
    from gecoscc.tasks import object_changed, object_created
    policy = policies_collection.find_one({'slug': slug})
    policy_id = unicode(policy.get('_id'))

    if use_celery:
        object_created = object_created.delay
        object_changed = object_changed.delay

    nodes_related_with_obj = nodes_collection.find({"policies.%s.object_related_list" % policy_id: {'$in': [unicode(obj['_id'])]}})

    if nodes_related_with_obj.count() == 0:
        return

    for node in nodes_related_with_obj:
        is_visible = is_object_visible(nodes_collection, object_related_id=obj['_id'],
                                       ou_id=node['path'].split(',')[-1], obj_id=node['_id'])

        if not is_visible:
            object_related_list = node['policies'][policy_id].get('object_related_list', [])
            object_related_list.remove(unicode(obj['_id']))

            if not object_related_list:
                del node['policies'][policy_id]
            else:
                node['policies'][policy_id]['object_related_list'] = object_related_list
            obj_related = update_collection_and_get_obj(nodes_collection, node['_id'], node['policies'])
            if obj_related['type'] in RESOURCES_RECEPTOR_TYPES:
                try:
                    func = globals()['update_data_%s' % obj_related['type']]
                except KeyError:
                    raise NotImplementedError
                func(nodes_collection, obj_related, policy, api, auth_user)
                if obj_related['type'] == 'user':
                    apply_policies_to_user(nodes_collection, obj_related, auth_user, api)
                if obj_related['type'] == 'computer':
                    apply_policies_to_computer(nodes_collection, obj_related, auth_user, api)

    object_created(auth_user, obj['type'], obj)


def apply_policies_to_group(nodes_collection, group, auth_user, api=None, initialize=False, use_celery=True, policies_collection=None):
    '''
    Checks if a group is within the scope of the objects that is related and then update policies
    '''
    from gecoscc.tasks import object_changed, object_created
    if use_celery:
        object_created = object_created.delay
        object_changed = object_changed.delay
    policies = group['policies'].keys()
    members_group = copy(group['members'])
    if not members_group:
        return
    for member_id in members_group:
        member = nodes_collection.find_one({'_id': member_id})
        is_visible = is_visible_group(nodes_collection.database, group['_id'], member)

        if not is_visible:

            member['memberof'].remove(group['_id'])
            user_member_of_groups = member['memberof']
            group['members'].remove(member['_id'])
            groups_members = group['members']
            nodes_collection.update({'_id': member_id, }, {'$set': {'memberof': user_member_of_groups}})
            nodes_collection.update({'_id': group['_id']}, {'$set': {'members': groups_members}})

            if member['type'] == 'user':
                update_data_user(nodes_collection, member, policies, api, auth_user)
                apply_policies_to_user(nodes_collection, member, auth_user, api)
            elif member['type'] == 'computer':
                update_data_computer(nodes_collection, member, policies, api, auth_user)

    object_created(auth_user, group['type'], group)


def apply_policies_to_ou(nodes_collection, ou, auth_user, api=None, initialize=False, use_celery=True, policies_collection=None):
    '''
    Checks if a group is within the scope of the objects that is related and then update policies
    '''
    from gecoscc.tasks import object_changed, object_created, object_moved
    if use_celery:
        object_created = object_created.delay
        object_changed = object_changed.delay
    children_path = ou['path'] + ',' + unicode(ou['_id'])
    ou_children = nodes_collection.find({'path': {'$regex': '.*' + unicode(ou['_id']) + '.*'}})

    visibility_object_related(nodes_collection.database, ou)

    if ou_children.count() == 0:
        return

    for child in ou_children:
        child_old = nodes_collection.find_one({'_id': child['_id']})
        child['path'] = children_path
        object_moved(auth_user, child['type'], child, child_old)

    object_created(auth_user, 'ou', ou)


def update_data_ou(nodes_collection, obj, policy, api, auth_user):
    members_path = obj['path'] + ',' + unicode(obj['_id'])
    members = nodes_collection.find({'path': members_path})

    for member in members:
        if member['type'] in RESOURCES_RECEPTOR_TYPES:
            try:
                func = globals()['update_data_%s' % member['type']]
            except KeyError:
                raise NotImplementedError
            func(nodes_collection, member, policy, api, auth_user)
            if member['type'] == 'user':
                apply_policies_to_user(nodes_collection, member, auth_user, api)
            if member['type'] == 'computer':
                apply_policies_to_computer(nodes_collection, member, auth_user, api)


def update_data_group(nodes_collection, obj, policy, api, auth_user):
    for member_id in obj['members']:
        member = nodes_collection.find_one({'_id': member_id})
        if member['type'] == 'user':
            update_data_user(nodes_collection, member, policy, api, auth_user)
        elif member['type'] == 'computer':
            update_data_computer(nodes_collection, member, policy, api)


def update_data_user(nodes_collection, obj, policy, api, auth_user):
    from gecoscc.tasks import object_changed, object_created
    computers = get_computer_of_user(nodes_collection, obj)
    if isinstance(policy, list):
        policy_field_name = []
        for policy_id in policy:
            policy = nodes_collection.database.policies.find_one({'_id': ObjectId(policy_id)})
            policy_field_name.append(policy['path'].split('.')[2])
    else:
        policy_field_name = [policy['path'].split('.')[2]]
    remove_chef_user_data(obj, computers, api, policy_field_name)
    object_created(auth_user, 'user', obj, computers=computers)
    object_changed(auth_user, 'user', obj, {}, computers=computers)


def update_data_computer(nodes_collection, obj, policy, api, auth_user):
    from gecoscc.tasks import object_created
    if policy and policy['slug'] != 'storage_can_view':
        if isinstance(policy, list):
            policy_field_name = []
            for policy_id in policy:
                policy = nodes_collection.database.policies.find_one({'_id': ObjectId(policy_id)})
                policy_field_name.append(policy['path'].split('.')[:3])
        else:
            policy_field_name = [policy['path'].split('.')[:3]]
        remove_chef_computer_data(obj, api, policy_field_name)
    object_created(auth_user, 'computer', obj, computers=[obj])


def apply_policies_to_printer(nodes_collection, printer, auth_user, api=None, initialize=False, use_celery=True, policies_collection=None):
    '''
    Checks if a printer is within the scope of the objects that is related and then update policies
    '''
    apply_policies_to_emitter_object(nodes_collection, printer, auth_user, 'printer_can_view', api, initialize, use_celery, policies_collection)


def apply_policies_to_repository(nodes_collection, repository, auth_user, api=None, initialize=False, use_celery=True, policies_collection=None):
    '''
    Checks if a repository is within the scope of the objects that is related and then update policies
    '''
    apply_policies_to_emitter_object(nodes_collection, repository, auth_user, 'repository_can_view', api, initialize, use_celery, policies_collection)


def apply_policies_to_storage(nodes_collection, storage, auth_user, api=None, initialize=False, use_celery=True, policies_collection=None):
    '''
    Checks if a storage is within the scope of the objects that is related and then update policies
    '''
    apply_policies_to_emitter_object(nodes_collection, storage, auth_user, 'storage_can_view', api, initialize, use_celery, policies_collection)


def remove_policies_of_computer(user, computer, auth_user):
    from gecoscc.tasks import object_deleted
    computer['user'] = user
    object_deleted.delay(auth_user, 'user', user, computers=[computer])


def get_pem_for_username(settings, username, pem_name):
    return open(get_pem_path_for_username(settings, toChefUsername(username), pem_name), 'r').read().encode('base64')


def get_pem_path_for_username(settings, username, pem_name):
    first_boot_media = settings.get('firstboot_api.media')
    user_media = os.path.join(first_boot_media, username)
    if not os.path.exists(user_media):
        os.makedirs(user_media)
    return os.path.join(user_media, pem_name)


def save_pem_for_username(settings, username, pem_name, pem_text):
    fileout = open(get_pem_path_for_username(settings, username, pem_name), 'w')
    fileout.write(pem_text)
    fileout.close()


def get_cookbook(api, cookbook_name):
    return api['/cookbooks/%s/_latest/' % cookbook_name]


def register_node(api, node_id, ou, collection_nodes):
    from gecoscc.models import Computer
    node = ChefNode(node_id, api)
    if not node.attributes.to_dict():
        return False
    try:
        computer_name = node.attributes.get_dotted('ohai_gecos.pclabel')
    except KeyError:
        computer_name = node_id
    comp_model = Computer()
    computer = comp_model.serialize({'path': '%s,%s' % (ou['path'], unicode(ou['_id'])),
                                     'name': computer_name,
                                     'type': 'computer',
                                     'source': ou.get('source', SOURCE_DEFAULT),
                                     'node_chef_id': node_id})
    del computer['_id']
    if check_unique_node_name_by_type_at_domain(collection_nodes, computer):
        if collection_nodes.find_one({'node_chef_id': node_id}):
            return 'duplicated-node-id'
        node_id = collection_nodes.insert(computer)
        return node_id
    return 'duplicated'


def update_node(api, node_id, ou, collection_nodes):
    from gecoscc.models import Computer
    node = ChefNode(node_id, api)
    if not node.attributes.to_dict():
        return False
    try:
        computer_name = node.attributes.get_dotted('ohai_gecos.pclabel')
    except KeyError:
        computer_name = node_id
    comp_model = Computer()
    computer = comp_model.serialize({'path': '%s,%s' % (ou['path'], unicode(ou['_id'])),
                                     'name': computer_name,
                                     'type': 'computer',
                                     'source': ou.get('source', SOURCE_DEFAULT),
                                     'node_chef_id': node_id})
    del computer['_id']
    node_id = collection_nodes.update({'node_chef_id': node_id},
                                      computer)
    return node_id


def register_or_updated_node(api, node_id, ou, collection_nodes):
    mongo_node = collection_nodes.find({'node_chef_id': node_id})
    if mongo_node:
        return update_node(api, node_id, ou, collection_nodes)
    return register_node(api, node_id, ou, collection_nodes)


def is_domain(node):
    return node['path'].count(',') == 1


def get_domain_path(node):
    return node['path'].split(',')[:3]


def get_domain(node, collection_node):
    domain = None
    try:
        path_split = node['path'].split(',')
        if len(path_split) >= 3:
            domain = collection_node.find_one({'_id': ObjectId(path_split[2])})
        elif len(path_split) == 2:
            domain = node
    except IndexError:
        pass
    return domain


def get_filter_in_domain(node):
    path_domain = get_domain_path(node)
    return {'$regex': '^%s' % ','.join(path_domain)}


def get_filter_this_domain(domain):
    path_domain = '%s,%s' % (domain['path'], unicode(domain['_id']))
    return {'$regex': '^%s' % path_domain}


def check_unique_node_name_by_type_at_domain(collection_nodes, obj):
    filters = {}
    levels = obj['path'].count(',')
    if levels >= 2:
        filters['path'] = get_filter_in_domain(obj)
    else:
        current_path = obj['path']
        filters['path'] = ','.join(current_path)

    filters['name'] = obj['name']
    filters['type'] = obj['type']

    if '_id' in obj:
        filters['_id'] = {'$ne': obj['_id']}
    return collection_nodes.find(filters).count() == 0


def _is_local_user(user):
    return user and user['type'] == 'user' and user['source'] == SOURCE_DEFAULT


def is_local_user(user, collection_nodes):
    is_local = _is_local_user(user)

    if is_local and '_id' in user:
        mongo_user = collection_nodes.find_one({'_id': user['_id']})
        is_local = _is_local_user(mongo_user)

    return is_local


# Transform an username into a Chef username
# by replacing the dots by "___"
def toChefUsername(username):
    return username.replace('.', '___')


# Transforms back a Chef username into a regular username
# by replacing the "___" by dots
def fromChefUsername(username):
    return username.replace('___', '.')


# Get the components of a URL
def getURLComponents(url):
    components = {}

    url_re = r"(?P<protocol>(http[s]?|ftp|mongodb))://((?P<user>[^:@]+)(:(?P<password>[^@]+))?@)?(?P<host_name>[^:/]+)(:(?P<port>[0-9]+))?(?P<path>[a-zA-Z0-9\/]+)?"
    m = re.match(url_re, url)
    components['protocol'] = m.group('protocol')
    components['host_name'] = m.group('host_name')
    components['port'] = m.group('port')
    components['path'] = m.group('path')
    components['user'] = m.group('user')
    components['password'] = m.group('password')

    if components['port'] is None:
        if components['protocol'] == 'ftp':
            components['port'] = '21'
        elif components['protocol'] == 'http':
            components['port'] = '80'
        elif components['protocol'] == 'https':
            components['port'] = '443'
        elif components['protocol'] == 'mongodb':
            components['port'] = '27017'

    return components

def update_computers_of_user(db, user, api):
    from gecoscc.api.chef_status import USERS_OHAI

    logger.warning("utils ::: update_computers_of_user - user = %s" % str(user))
    nodes = db.nodes.find({'path': {'$regex': '.*' + user['path'] +'.*'}, 'type':'computer'})

    for node in nodes:
        chef_node = ChefNode(node['node_chef_id'], api)
        try:
            users = chef_node.attributes.get_dotted(USERS_OHAI)
        except KeyError:
            users = []

        if any(usr['username'] == user['name'] for usr in users):
            if node['_id'] not in user['computers']:
                user['computers'].append(node['_id'])

    return user
