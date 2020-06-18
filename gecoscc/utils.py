# -*- coding: utf-8 -*-

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
import sys
import pytz
import random
import string
import time
import re
import pkg_resources
import logging
import subprocess
import traceback

from gettext import gettext as _
from bson import ObjectId, json_util
from copy import deepcopy, copy

from chef import ChefAPI, Client
from chef import Node as ChefNode
from chef.exceptions import ChefError
from chef.node import NodeAttributes

from pyramid.threadlocal import get_current_registry

from collections import defaultdict
from pymongo.collation import Collation, CollationStrength

import requests
from requests.packages.urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(InsecureRequestWarning)


DELETED_POLICY_ACTION = 'deleted'

RESOURCES_RECEPTOR_TYPES = ('computer', 'ou', 'user', 'group')
RESOURCES_EMITTERS_TYPES = ('printer', 'storage', 'repository')
POLICY_EMITTER_SUBFIX = '_can_view'
USER_MGMT = 'users_mgmt'
SOURCE_DEFAULT = MASTER_DEFAULT = 'gecos'
USE_NODE = 'use_node'

# Updates patterns
BASE_UPDATE_PATTERN = '^update-(\w+)\.zip$'
SERIALIZED_UPDATE_PATTERN = '^update-[0-9]{4}\.zip$'


# Reserved codes for functions called from scripts
SCRIPTCODES = { 
    'mongodb_backup':'00',
    'chefserver_backup': '00',
    'upload_cookbook':'25',
    'import_policies': '26',
    'mongodb_restore':'99',
    'chefserver_restore':'99'}
    
AUDIT_ACTIONS = [ 'login','logout','expire' ]

logging.basicConfig(level=logging.INFO)
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
        # Sudoers
        if user['name'] in computer.get('sudoers',[]):
            continue
            
        computer['user'] = user
        if computer not in related_computers:
            related_computers.append(computer)
            
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
        'name': ou['name'], 'path': ou['path']} for ou in ous]


def emiter_police_slug(emiter_type):
    return '%s%s' % (emiter_type, POLICY_EMITTER_SUBFIX)


def oids_filter(request):
    oids = request.GET.get('oids')
    return {
        '$or': [{'_id': ObjectId(oid)} for oid in oids.split(',')]
    }

# Chef utils


def password_generator(size=8, chars=string.ascii_lowercase + string.digits):
    return ''.join(random.choice(chars) for _ in range(size))


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


def delete_chef_admin_user(api, usrname):
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
    for _attempt in range(attempts):
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
    both a and b have a key who's value is a dict then dict_merge is called
    on both values and the result stored in the returned dictionary.'''
    if not isinstance(b, dict):
        return b
    result = a.copy()
    for k, v in b.iteritems():
        if k in result and isinstance(result[k], dict):
                result[k] = dict_merge(result[k], v)
        elif isinstance(v, list):
            result[k] = list(v)
        else:
            result[k] = v
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
            if not group:
                # Group not found in database
                continue
            
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


def recalc_node_policies(nodes_collection, jobs_collection, computer, auth_user,
                         cookbook_name, api=None, cookbook=None,
                         validator=None,
                         initialize=True, use_celery=False):
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
                               cookbook=cookbook,
                               initialize=initialize,
                               use_celery=use_celery,
                               calculate_inheritance=False,
                               validator=validator)
    
    # Mark the OUs of this computer as already visited
    ous_already_visited = []
    ous = nodes_collection.find(get_filter_ous_from_path(computer['path']))
    for ou in ous:
        if ou.get('policies', {}):    
            oid = str(ou['_id'])
            ous_already_visited.append(oid)
    
    users = nodes_collection.find({'type': 'user', 'computers': computer['_id']})
    for user in users:
        apply_policies_to_user(nodes_collection, user, auth_user, api,
                               [computer],
                               cookbook=cookbook,
                               initialize=initialize,
                               use_celery=use_celery,
                               ous_already_visited=ous_already_visited,
                               calculate_inheritance=False,
                               validator=validator)
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


def apply_policies_to_computer(nodes_collection, computer, auth_user, api=None,
        cookbook=None, initialize=False, use_celery=True,
        policies_collection=None,
        calculate_inheritance=True,
        validator=None):
    from gecoscc.tasks import object_changed, object_created
    logger.info('apply_policies_to_computer: %s'%(computer['name']))
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
            object_changed(auth_user, 'ou', ou, {}, computers=[computer],
                           api=api, cookbook=cookbook,
                           calculate_inheritance=calculate_inheritance,
                           validator=validator)

    groups = nodes_collection.find({'_id': {'$in': computer.get('memberof', [])}})
    for group in groups:
        if group.get('policies', {}):
            object_changed(auth_user, 'group', group, {}, computers=[computer],
                           api=api, cookbook=cookbook,
                           calculate_inheritance=calculate_inheritance,
                           validator=validator)

    object_created(auth_user, 'computer', computer, computers=[computer],
                   api=api, cookbook=cookbook,
                   calculate_inheritance=calculate_inheritance,
                   validator=validator)


def apply_policies_to_user(nodes_collection, user, auth_user, api=None,
                           computers=None, cookbook=None,
                           initialize=False, use_celery=True,
                           policies_collection=None,
                           ous_already_visited=[],
                           calculate_inheritance=True,
                           validator=None):
    from gecoscc.tasks import object_changed, object_created
    logger.info('apply_policies_to_user: %s'%(user['name']))
    if use_celery:
        object_created = object_created.delay
        object_changed = object_changed.delay

    if computers is None:
        computers = get_computer_of_user(nodes_collection, user)

    if api and initialize:
        user = visibility_group(nodes_collection.database, user)
        user = visibility_object_related(nodes_collection.database, user)
        remove_chef_user_data(user, computers, api)

    if not computers:
        return

    ous = nodes_collection.find(get_filter_ous_from_path(user['path']))
    for ou in ous:
        oid = str(ou['_id'])
        if ou.get('policies', {}) and (oid not in ous_already_visited):
            ous_already_visited.append(oid)
            object_changed(auth_user, 'ou', ou, {}, computers=computers,
                           api=api, cookbook=cookbook,
                           calculate_inheritance=calculate_inheritance,
                           validator=validator)

    groups = nodes_collection.find({'_id': {'$in': user.get('memberof', [])}})
    for group in groups:
        if group.get('policies', {}):
            object_changed(auth_user, 'group', group, {}, computers=computers,
                           api=api, cookbook=cookbook,
                           calculate_inheritance=calculate_inheritance,
                           validator=validator)

    object_created(auth_user, 'user', user, computers=computers,
                   api=api, cookbook=cookbook,
                   calculate_inheritance=calculate_inheritance,
                   validator=validator)


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
    # From the pymongo documentation:
    # Cursors in MongoDB can timeout on the server if they have been open for a long time without any operations being 
    # performed on them. This can lead to an CursorNotFound exception being raised when attempting to iterate the cursor.
    # OUs with a lot of depth levels
    ou_children = nodes_collection.find({'path': {'$regex': '.*' + unicode(ou['_id']) + '.*'}}, no_cursor_timeout=True)

    visibility_object_related(nodes_collection.database, ou)

    if ou_children.count() == 0:
        logger.debug("utils ::: apply_policies_to_ou - OU without children = %s" % str(ou['name']))
        object_created(auth_user, 'ou', ou)
        return

    for child in ou_children:
        child_old = nodes_collection.find_one({'_id': child['_id']})
        child['path'] = children_path
        object_moved(auth_user, child['type'], child, child_old)

    # Closes pymongo cursor
    ou_children.close()
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
            update_data_computer(nodes_collection, member, policy, api, auth_user)


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

class setPathAttrsToNodeException(Exception):
    pass

def add_path_attrs_to_node(node, strpath, collection, save=True):
    ''' Setting up gecos_path_ids, gecos_path_names attributes to Chef node '''

    logger.debug("utils ::: add_path_chef_node - node_id = {}".format(
        str(node)))
    logger.debug("utils ::: add_path_chef_node - strpath = {}".format(strpath))

    pathnames = 'root'
    for elm in strpath.split(','):
        if elm == 'root':
            continue
        ou = collection.find_one({'_id': ObjectId(elm)})
        pathnames += ',' + ou['name'] 

    logger.debug("utils ::: add_path_chef_node - pathnames = {}".format(
        pathnames))

    try:
        node.attributes.set_dotted('gecos_path_ids', strpath)
        node.attributes.set_dotted('gecos_path_names', pathnames)
        if save:
            node.save()
    except (TypeError, KeyError, ChefError) as e:
        logger.error("utils ::: add_path_chef_node - Exception to setting up"\
                     " path in chef node: {}".format(e))
        raise setPathAttrsToNodeException

def register_node(api, node_id, ou, collection_nodes):
    from gecoscc.models import Computer

    ret = False
    node = ChefNode(node_id, api)

    if node.attributes.to_dict():
        try:
            computer_name = node.attributes.get_dotted('ohai_gecos.pclabel')
        except KeyError:
            computer_name = node_id

        try:
            nodepath = '{},{}'.format(ou['path'], unicode(ou['_id']))
            add_path_attrs_to_node(node, nodepath, collection_nodes)

            comp_model = Computer()
            computer = comp_model.serialize({'path': nodepath,
                                             'name': computer_name,
                                             'type': 'computer',
                                             'source': ou.get('source', SOURCE_DEFAULT),
                                             'node_chef_id': node_id})
            del computer['_id']
            if check_unique_node_name_by_type_at_domain(collection_nodes, computer):
                if collection_nodes.find_one({'node_chef_id': node_id}):
                    ret = 'duplicated-node-id'
                else:
                    node_id = collection_nodes.insert(computer)
                    ret = node_id
            else:
                ret = 'duplicated'

        except setPathAttrsToNodeException:
            ret = 'path-err'

    return ret

def update_node(api, node_id, ou, collection_nodes):
    from gecoscc.models import Computer

    ret = False
    node = ChefNode(node_id, api)

    if node.attributes.to_dict():
        try:
            computer_name = node.attributes.get_dotted('ohai_gecos.pclabel')
        except KeyError:
            computer_name = node_id

        try:
            nodepath = '{},{}'.format(ou['path'], unicode(ou['_id']))
            add_path_attrs_to_node(node, nodepath, collection_nodes)

            comp_model = Computer()
            computer = comp_model.serialize({'path': nodepath,
                                             'name': computer_name,
                                             'type': 'computer',
                                             'source': ou.get('source', SOURCE_DEFAULT),
                                             'node_chef_id': node_id})
            del computer['_id']
            ret = collection_nodes.update({'node_chef_id': node_id}, computer)

        except setPathAttrsToNodeException:
            logger.error('utils.py ::: update_node - Exception adding gecos_path info to chef node')

    return ret

def register_or_updated_node(api, node_id, ou, collection_nodes):
    mongo_node = collection_nodes.find({'node_chef_id': node_id})
    if mongo_node:
        return update_node(api, node_id, ou, collection_nodes)
    return register_node(api, node_id, ou, collection_nodes)


def is_root(node):
    return node['path'].count(',') == 0

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

# TODO: Replace this line with lines below when MongoDB 3.4 is available
    return collection_nodes.find(filters).count() == 0
    
#    count = 0
#    settings = get_current_registry().settings
#    locales = settings['pyramid.locales']
#    for lang in locales:
#        # Check that the name is unique in every locale
#        count = count + collection_nodes.find(filters).collation(
#            Collation(locale=lang, strength=CollationStrength.PRIMARY)).count()
    
#    return count == 0


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

    logger.debug("utils ::: update_computers_of_user - user = %s" % str(user))
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

def nested_lookup(key, document):
    """Lookup a key in a nested document, return a list of values"""
    return list(_nested_lookup(key, document))

def _nested_lookup(key, document):
    """Lookup a key in a nested document, yield a value"""
    from six import iteritems

    if isinstance(document, list):
        for d in document:
            for result in _nested_lookup(key, d):
                yield result

    if isinstance(document, dict):
        for k, v in iteritems(document):
            if k == key:
                yield v
            elif isinstance(v, dict):
                for result in _nested_lookup(key, v):
                    yield result
            elif isinstance(v, list):
                for d in v:
                    for result in _nested_lookup(key, d):
                        yield result

# ------------------------------------------------------------------------------------------------------
def order_groups_by_depth(db, groups_ids):
    """Function that orders a group list by depth.
        (when several groups have the same depth they will be ordered in alphabetic order).

    Args:
        db (object): Mongo DB access object.
        groups_ids (list): List of group IDs.

    Returns:
        list: Sorted list.

    """
    
    # Parameter checking
    if db is None:
        raise ValueError('db is None')

    if groups_ids is None:
        raise ValueError('groups_ids is None')

    if not isinstance(groups_ids, list):
        raise ValueError('groups_ids is not a list')      
    
    groups_ids = [ObjectId(groups_id) for groups_id in groups_ids]
    groups = [group for group in db.nodes.find({'_id': {'$in': groups_ids}, 'type': 'group'}).sort([('name',-1)])]
    groups.sort(key=lambda x: x['path'].count(','), reverse=True)
    return [unicode(group['_id']) for group in groups]

# ------------------------------------------------------------------------------------------------------
def order_ou_by_depth(db, ou_ids):
    """Function that orders an ou list by depth.

    Args:
        db (object): Mongo DB access object.
        ou_ids (list): List of OU IDs.

    Returns:
        list: Sorted list.

    """
    
    # Parameter checking
    if db is None:
        raise ValueError('db is None')

    if ou_ids is None:
        raise ValueError('ou_ids is None')

    if not isinstance(ou_ids, list):
        raise ValueError('ou_ids is not a list')          
    
    ou_ids = [ObjectId(ou_id) for ou_id in ou_ids]
    ous = [ou for ou in db.nodes.find({'_id': {'$in': ou_ids}, 'type': 'ou'})]
    ous.sort(key=lambda x: x['path'].count(','), reverse=True)
    return [unicode(ou['_id']) for ou in ous]

# ------------------------------------------------------------------------------------------------------
def get_priority_node(db, nodes_list):
    """Function that the object with the top priority of the list.

    Args:
        db (object): Mongo DB access object.    
        nodes_list (list): List of node IDs.

    Returns:
        object: Object with the top priority or None if no object is found.

    """
    # Parameter checking
    if db is None:
        raise ValueError('db is None')

    if nodes_list is None:
        raise ValueError('nodes_list is None')

    if not isinstance(nodes_list, list):
        raise ValueError('nodes_list is not a list')         
        
    priority_node = None

    # Check if there is a computer in the list
    nodes_ids = [ObjectId(node_id) for node_id in nodes_list]
    computers = [computer for computer in db.nodes.find({'_id': {'$in': nodes_ids}, 'type': 'computer'})]
    if len(computers) > 0:
        priority_node = str(computers[0]['_id'])
    
    if priority_node is None:
        # Check if there is an user in the list
        users = [user for user in db.nodes.find({'_id': {'$in': nodes_ids}, 'type': 'user'})]
        if len(users) > 0:
            priority_node = str(users[0]['_id'])
        
    if priority_node is None:
        # Check if there is an group in the list
        groups = order_groups_by_depth(db, nodes_list)
        if len(groups) > 0:
            priority_node = groups[0]
        
    if priority_node is None:
        # Check if there is an OU in the list
        ous = order_ou_by_depth(db, nodes_list)
        if len(ous) > 0:
            priority_node = ous[0]
            
    return priority_node

# ------------------------------------------------------------------------------------------------------
def set_inherited_field(logger, inheritanceTree, policy_id, false_node_list, priority_node_id):
    """Function that looks into the inheritanceTree and set the 'inherited' field of a policy to false
       if a node is in the "false_node_list" or to true if the node is the "priority_node_id"

    Args:
        logger (object): Logger.
        inheritanceTree (object): Tree of inheritance objects
        policy_id (string): Policy ID of the policy that is changed or deleted.
        false_node_list (list): List of node IDs to set the 'inherited' field to False
        priority_node_id (string): Node ID to set the 'inherited' field to True

    Returns:
        Nothing.

    """
    # Parameter checking
    if logger is None:
        raise ValueError('logger is None')

    if inheritanceTree is None:
        raise ValueError('inheritanceTree is None')

    if policy_id is None:
        raise ValueError('policy_id is None')

    if not isinstance(policy_id, str):
        raise ValueError('policy_id is not a string')         
        
    if false_node_list is None:
        raise ValueError('false_node_list is None')

    if not isinstance(false_node_list, list):
        raise ValueError('false_node_list is not a list')         
        
    if priority_node_id is None:
        raise ValueError('priority_node_id is None')
        
    if not isinstance(priority_node_id, str):
        raise ValueError('priority_node_id is not a string')         

        
    logger.debug("utils.py ::: set_inherited_field - inheritanceTree['_id'] = {0} priority_node_id={1} policy_id? {2} is_main_element? {3}".format(
        inheritanceTree['_id'], priority_node_id, (policy_id in inheritanceTree['policies']), inheritanceTree['is_main_element']))    
    if policy_id in inheritanceTree['policies']:
        if str(inheritanceTree['_id']) == str(priority_node_id) and inheritanceTree['is_main_element']:
            inheritanceTree['policies'][policy_id]['inherited'] = True
            logger.debug("utils.py ::: set_inherited_field - Set as inherited ({0}, {1})!".format(priority_node_id, policy_id))    
        elif str(inheritanceTree['_id']) in false_node_list and inheritanceTree['is_main_element']:
            inheritanceTree['policies'][policy_id]['inherited'] = False
    
    for child in inheritanceTree['children']:
        set_inherited_field(logger, child, policy_id, false_node_list, priority_node_id)

    
# ------------------------------------------------------------------------------------------------------
def get_inheritance_tree_node_list(inheritanceTree, policy_id):
    """Function that retuns a list with all the IDs of all nodes in an inheritance Tree with the policy specified.

    Args:
        inheritanceTree (object): Tree of inheritance objects
        policy_id (string): Policy ID of the policy that is changed or deleted.

    Returns:
        tree_node_list: List with all the IDs of all nodes in an inheritance tree with that policy.

    """
    # Parameter checking
    if inheritanceTree is None:
        raise ValueError('inheritanceTree is None')

    if policy_id is None:
        raise ValueError('policy_id is None')

    if not isinstance(policy_id, str):
        raise ValueError('policy_id is not a string')       
    
    
    tree_node_list = []
    
    # Chef if the policy id exists
    exists = False
    for p_id in inheritanceTree['policies']:
        if policy_id == p_id:
            exists = True
            break    
    
    if exists:
        tree_node_list.append(inheritanceTree['_id'])
        
    for child in inheritanceTree['children']:
        tree_node_list.extend(get_inheritance_tree_node_list(child, policy_id))

    return tree_node_list        

# ------------------------------------------------------------------------------------------------------
def get_inheritance_tree_policies_list(inheritanceTree, policies_list):
    """Function that retuns a list with all the policies of all nodes in an inheritance Tree.

    Args:
        inheritanceTree (object): Tree of inheritance objects
        policies_list: List with policies found until this moment.

    Returns:
        policies_list: List with all the policies in an inheritance tree.

    """
    # Parameter checking
    if inheritanceTree is None:
        raise ValueError('inheritanceTree is None')
    
    
    if 'policies' in inheritanceTree:
        for policy_id in inheritanceTree['policies']:
            exist = False
            for policy in policies_list:
                if policy['_id'] == policy_id:
                    exist = True
                    break
                    
            if not exist:
                policy = deepcopy(inheritanceTree['policies'][policy_id])
                policy['_id'] = policy_id
                policies_list.append(policy)
    
    if 'children' in inheritanceTree:
        for child in inheritanceTree['children']:
            get_inheritance_tree_policies_list(child, policies_list)

    return policies_list 
    
    

# ------------------------------------------------------------------------------------------------------
def recalculate_path_values(logger, inheritanceTree, path_value, main_ou_list):
    """Recalculate the 'path' value in every node in the inheritance Tree.

    Args:
        logger (object): Logger.
        inheritanceTree (object): Tree of inheritance objects.
        path_value (string): Path up to this node.
        main_ou_list (list): List of previous OUs that are "main_element"
        

    Returns:
        nothing

    """
    # Parameter checking
    if logger is None:
        raise ValueError('logger is None')    
        
    if path_value is None:
        raise ValueError('path_value is None')            
        
    if inheritanceTree is None:
        raise ValueError('inheritanceTree is None')    

    if inheritanceTree['is_main_element']:
        # Use the received path value
        inheritanceTree['path'] = path_value
        if inheritanceTree['type'] == 'ou':
            main_ou_list.append(inheritanceTree)
            
    else:
        # Copy the path of the main element
        for ou in main_ou_list:
            if ou['_id'] == inheritanceTree['_id']:
                inheritanceTree['path'] = ou['path']
            
    
    # Recalculate path values for the children
    for child in inheritanceTree['children']:
        pv = path_value
        if inheritanceTree['is_main_element']:
            pv = ('%s,%s'%(path_value, inheritanceTree['_id']))
        
        if child['type'] == 'group':
            pv = ('%s,%s'%(inheritanceTree['path'], inheritanceTree['_id']))
            
        recalculate_path_values(logger, child, pv, main_ou_list)

# ------------------------------------------------------------------------------------------------------
def move_in_inheritance(logger, db, obj, inheritanceTree):
    """Move an object to another position in the inheritance Tree.

    Args:
        logger (object): Logger.
        db (object): Mongo DB access object.
        obj (object): Node (computer, user, OU or group) that received the change.
        inheritanceTree (object): Tree of inheritance objects

    Returns:
        nodes_added: The return value. A list of nodes added to the inheritance tree.

    """
    # Parameter checking
    if logger is None:
        raise ValueError('logger is None')    
        
    if db is None:
        raise ValueError('db is None')    
        
    if obj is None:
        raise ValueError('obj is None')    
        
    if inheritanceTree is None:
        raise ValueError('inheritanceTree is None')    
    
    nodes_added = []
            
    logger.debug("utils.py ::: move_in_inheritance - obj=%s" %(obj['name']))
    if inheritanceTree['_id'] == str(obj['_id']):
        # This is the object to move
        
        if inheritanceTree['type'] == 'group':
            # A group does not inherit nothing
            inheritanceTree['path'] = obj['path']
            
        else:
            # Must move the object to a different place of the tree
            
            # Look for the base node and remove unnecessary branches
            base_node = inheritanceTree['parent']
            while ('parent' in base_node) and not ((base_node['_id'] in obj['path']) and base_node['is_main_element']):
                logger.debug("utils.py ::: move_in_inheritance - remove %s from path" %(base_node['_id']))
                base_node['parent']['children'].remove(base_node)
                base_node = base_node['parent']
            
            # Add the necessary OUs to the tree
            previousOU = base_node
            base_node_path = base_node['path']+','+base_node['_id']
            obj_path = obj['path']
            logger.debug("utils.py ::: move_in_inheritance - obj_path=%s base_node_path=%s" %(obj_path, base_node_path))
            
            
            if not obj_path.startswith(base_node_path):
                # Moving an OU (base_node) to a different place in the nodes tree
                root_node = base_node['parent']
                while 'parent' in root_node:
                    root_node = root_node['parent']
                
                real_base_node = db.nodes.find_one({'_id': ObjectId(base_node['_id'])})
                if not real_base_node:
                    logger.error("utils.py ::: move_in_inheritance - real base node not found %s" % str(base_node['_id']))
                    return False                
                
                result = move_in_inheritance(logger, db, real_base_node, root_node)
                if result:
                    nodes_added.extend(result)
                    
                recalculate_path_values(logger, root_node, 'root', [])
                base_node_path = base_node['path']+','+base_node['_id']
                logger.debug("utils.py ::: move_in_inheritance - new obj_path=%s base_node_path=%s" %(obj_path, base_node_path))
            
            
            
            # Moving a node to a different place in the nodes tree
            obj_path = obj_path[len(base_node_path+','):].strip()
            logger.debug("utils.py ::: move_in_inheritance - final obj_path=%s" %(obj_path))

            # Ignore empty string
            if obj_path:
                for ou_id in obj_path.split(','):
                    if not ou_id:
                        # Ignore empty string
                        continue
                        
                    # Get ou from mongoDB
                    logger.debug("utils.py ::: move_in_inheritance - final ou_id=%s" %(ou_id))
                    ou = db.nodes.find_one({'_id': ObjectId(ou_id)})
                    if not ou:
                        logger.error("utils.py ::: move_in_inheritance - OU not found %s" % str(ou_id))
                        return False
                        
                    else:
                        # Generate item
                        item =  {}
                        item['_id'] = str(ou_id)
                        item['name'] = ou['name']
                        logger.debug("utils.py ::: move_in_inheritance - add_node=%s - %s"%(item['_id'], item['name']))
                        item['type'] = ou['type']
                        item['path'] = ou['path']
                        item['policies'] = {}
                        item['is_main_element'] = True
                        item['children'] = []
                        
                        if inheritanceTree is None:
                            inheritanceTree = item
                        
                        if previousOU is not None:
                            previousOU['children'].append(item)
                        
                        previousOU = item
                        nodes_added.append(item['_id'])
            
            # Move this node to the new OU
            previousOU['children'].append(inheritanceTree)
            inheritanceTree['parent']['children'].remove(inheritanceTree)

        
    else:
        for child in inheritanceTree['children']:
            # Check if child['parent'] already exists
            key_exists = ('parent' in child)
            
            child['parent'] = inheritanceTree
            result = move_in_inheritance(logger, db, obj, child)
            if result:
                # Result may be False in case of error
                nodes_added.extend(result)
                
            if not key_exists and ('parent' in child):
                # child['parent'] was added in this loop
                del child['parent']

    logger.debug("utils.py ::: move_in_inheritance - nodes_added={0}".format(nodes_added))
                
    return nodes_added      
    
# ------------------------------------------------------------------------------------------------------
def recalculate_policies_for_computers(logger, db, srcobj, computers):
    """Recalculate the policies of the object in the inheritance tree of
    the computers list.

    Args:
        logger (object): Logger.
        db (object): Mongo DB access object.
        srcobj (object): Node (computer, user, OU or group) that contains the policies.
        computers (object): Computers list wich inheritance tree must be updated.

    Returns:
        bool: The return value. True if success, false otherwise.

    """
    # Parameter checking
    if logger is None:
        raise ValueError('logger is None')    
        
    if db is None:
        raise ValueError('db is None')    
        
    if srcobj is None:
        raise ValueError('obj is None')    

    if computers is None:
        raise ValueError('obj is None')    
    
    logger.debug("recalculate_policies_for_computers - source node name=%s type=%s"%(srcobj['name'], srcobj['type']))
    
    for computer in computers:
        obj = computer
        if 'user' in computer:
            # Policies that affect to the user aren't displayed in the 
            # computer's inheritance tab
            continue 

        logger.debug("recalculate_policies_for_computers - recalculate for node: name=%s type=%s"%(obj['name'], obj['type']))
        
        # Calculate inheritance tree for the first time when neccessary
        if not calculate_initial_inheritance_for_node(logger, db, obj):
            return False
        
        # Recalculate policies for the source node
        for policy_id in srcobj['policies']:
            policydata = db.policies.find_one({'_id': ObjectId(policy_id)})
            if not policydata:
                logger.error("recalculate_policies_for_computers - Policy not found %s" % str(policy_id))
                return False             
                
            trace_inheritance(logger, db, 'change', srcobj, policydata)                
        
        # Finaly recalculate the 'inherited' field of all the non mergeable policies
        recalculate_inherited_field(logger, db, str(obj['_id']))   
    
    return True


# ------------------------------------------------------------------------------------------------------
def move_in_inheritance_and_recalculate_policies(logger, db, srcobj, obj):
    """Move an object to another position in the inheritance Tree and recalculate
       the policies of the added nodes.

    Args:
        logger (object): Logger.
        db (object): Mongo DB access object.
        srcobj (object): Node (computer, user, OU or group) that is moved.
        obj (object): Node (computer, user, OU or group) which inheritance tree must be updated.

    Returns:
        bool: The return value. True if success, false otherwise.

    """
    # Parameter checking
    if logger is None:
        raise ValueError('logger is None')    
        
    if db is None:
        raise ValueError('db is None')    
        
    if srcobj is None:
        raise ValueError('obj is None')    

    if obj is None:
        raise ValueError('obj is None')    
    
    logger.debug("move_in_inheritance_and_recalculate_policies - Node name=%s type=%s"%(obj['name'], obj['type']))
    
    # Calculate inheritance tree for the first time when neccessary
    if not calculate_initial_inheritance_for_node(logger, db, obj):
        return False
    
    # The object is being moved to a new position in the nodes tree
    nodes_added = move_in_inheritance(logger, db, srcobj, obj['inheritance'])
    
    # Recalculate path values
    recalculate_path_values(logger, obj['inheritance'], 'root', [])
    
    # Update node in mongo db
    db.nodes.update({'_id': obj['_id']}, {'$set':{'inheritance': obj['inheritance']}})
    
    # Recalculate policies for each added node
    for newnode_id in nodes_added:
        newnode = db.nodes.find_one({'_id': ObjectId(newnode_id)})
        if not newnode:
            logger.error("move_in_inheritance_and_recalculate_policies - Node not found  %s" % str(newnode_id))
            return False                
            
        for policy_id in newnode['policies']:
            policydata = db.policies.find_one({'_id': ObjectId(policy_id)})
            if not policydata:
                logger.error("move_in_inheritance_and_recalculate_policies - Policy not found %s" % str(policy_id))
                return False             
                
            trace_inheritance(logger, db, 'change', newnode, policydata)                
    
    # Recalculate policies for the path
    for ou_id in obj['path'].split(','):
        if ou_id == 'root':
            continue
        
        ou = db.nodes.find_one({'_id': ObjectId(ou_id)})
        if not ou:
            logger.error("move_in_inheritance_and_recalculate_policies - OU not found  %s" % str(ou_id))
            return False                
            
        for policy_id in  ou['policies']:
            policydata = db.policies.find_one({'_id': ObjectId(policy_id)})
            if not policydata:
                logger.error("move_in_inheritance_and_recalculate_policies - Policy not found %s" % str(policy_id))
                return False             
                
            recalculate_inheritance_for_node(logger, db, 'change', ou, policydata, obj)
    
    # If the object is a computer or an user and belongs to any group
    # we have to ensure that all the groups appears after the last OU
    if (obj['type'] == 'user' or obj['type'] == 'computer') and len(obj.get('memberof', []))>0:
        # The easiest way to do this is to remove all the groups and add them again
        todelete = list(db.nodes.find( {'_id'  : {'$in': obj.get('memberof', [])}, 'type': 'group'} ))
        toadd = []
        for group in todelete:
            remove_group_from_inheritance_tree(logger, db, group, obj['inheritance'])
            toadd.append(group)
            
        for group in toadd:
            add_group_to_inheritance_tree(logger, db, group, obj['inheritance'])
            
            if 'policies' in group:
                for policy_id in group['policies'].keys():
                    policy = db.policies.find_one({"_id": ObjectId(policy_id)})
                    recalculate_inheritance_for_node(logger, db, 'changed', group, policy, obj)            
            
        # Recalculate path values
        recalculate_path_values(logger, obj['inheritance'], 'root', [])
        
        # Update node in mongo db
        db.nodes.update({'_id': obj['_id']}, {'$set':{'inheritance': obj['inheritance']}})
        
    
    # Finaly recalculate the 'inherited' field of all the non mergeable policies
    recalculate_inherited_field(logger, db, str(obj['_id']))   
    
    
    if obj['type'] == 'group' and len(obj.get('members', []))>0:
        # Moving a group means moving that group in the inheritance tree of all the related objects
        members = list(db.nodes.find( {'_id'  : {'$in': obj.get('members', [])}, 'type':{'$in': ['user', 'computer']}} ))
        for member in members:
            # Since the groups needs a no "is_main_element" OU we can't simply do:
            #     move_in_inheritance_and_recalculate_policies(logger, db, srcobj, member)
            #
            # So lets delete and create again the group 
            remove_group_from_inheritance_tree(logger, db, srcobj, member['inheritance'])
            add_group_to_inheritance_tree(logger, db, srcobj, member['inheritance'])
            
            if 'policies' in obj:
                for policy_id in obj['policies'].keys():
                    policy = db.policies.find_one({"_id": ObjectId(policy_id)})
                    recalculate_inheritance_for_node(logger, db, 'changed', obj, policy, member)            
            
            # Update node in mongo db
            db.nodes.update({'_id': member['_id']}, {'$set':{'inheritance': member['inheritance']}})
    
    return True
    
# ------------------------------------------------------------------------------------------------------
def exist_node_in_inheritance_tree(node, inheritanceTree):
    """Function that checks if a node exists in the inheritance tree of another node.

    Args:
        node (object): Node (OU, group, computer or user) to find.
        inheritanceTree (object): Tree of inheritance objects

    Returns:
        bool: The return value. True if exists, false otherwise.

    """
    # Parameter checking
    if not node or not inheritanceTree:
        return False
    
    if str(inheritanceTree['_id']) == str(node['_id']):
        return True

    found = False
    for child in inheritanceTree['children']:
        found = exist_node_in_inheritance_tree(node, child)
        if found:
            break
    
    return found
    
# ------------------------------------------------------------------------------------------------------
def remove_group_from_inheritance_tree(logger, db, group, inheritanceTree):
    """Function that remove a group from the inheritance tree of an object.

    Args:
        logger (object): Logger.
        db (object): Mongo DB access object.
        group (object): Group object to remove.
        inheritanceTree (object): Tree of inheritance objects

    Returns:
        bool: The return value. True for success, False otherwise.

    """
    # Parameter checking
    if logger is None:
        raise ValueError('logger is None')    
        
    if db is None:
        raise ValueError('db is None')    
        
    if group is None:
        raise ValueError('group is None')    
        
    if inheritanceTree is None:
        raise ValueError('inheritanceTree is None')     
    
    if not exist_node_in_inheritance_tree(group, inheritanceTree):
        # The group doesn't exist
        return False
    
    found = False
    logger.debug("utils.py ::: remove_group_from_inheritance_tree - group['_id'] = {0}".format(group['_id']))

    if inheritanceTree['_id'] == str(group['_id']):
        found = True
        # Remove this node
        base_node = inheritanceTree['parent']
        base_node['children'].remove(inheritanceTree)
        
        if len(base_node['children']) == 1:
            # Only 1 node is left. That node must be a computer, a user or another ou
            # --> Remove the base node too!
            base_node_parent = base_node['parent']
            base_node_parent['children'].append(base_node['children'][0])
            base_node_parent['children'].remove(base_node)
            
        if len(base_node['children']) == 0:
            # Strange. This must be caused by a previous error.
            # --> Remove it anyway!
            base_node_parent = base_node['parent']
            base_node_parent['children'].remove(base_node)            
    
    else:
        # Continue looking in the tree
        for child in inheritanceTree['children']:
            child['parent'] = inheritanceTree
            found = (found or remove_group_from_inheritance_tree(logger, db, group, child))
            del child['parent']
            if found:
                break
    
    return found
    
    
# ------------------------------------------------------------------------------------------------------
def add_group_to_inheritance_tree(logger, db, group, inheritanceTree):
    """Function that adds a group to the inheritance tree of an object.

    Args:
        logger (object): Logger.
        db (object): Mongo DB access object.
        group (object): Group object to add.
        inheritanceTree (object): Tree of inheritance objects

    Returns:
        bool: The return value. True for success, False otherwise.

    """
    # Parameter checking
    if logger is None:
        raise ValueError('logger is None')    
        
    if db is None:
        raise ValueError('db is None')    
        
    if group is None:
        raise ValueError('group is None')    
        
    if inheritanceTree is None:
        raise ValueError('inheritanceTree is None')     
    
    if exist_node_in_inheritance_tree(group, inheritanceTree):
        # The group already exist
        return False
    
    logger.debug("utils.py ::: add_group_to_inheritance_tree - group['_id'] = {0} group['path'] = {1}".format(group['_id'], group['path']))
    # Locate the base node
    base_node = inheritanceTree
    group_path = [groups_id for groups_id in reversed(group['path'].split(','))]
    logger.debug("utils.py ::: add_group_to_inheritance_tree - group_path={0}".format(group_path))
    group_base_node_id = group_path[0]
    logger.debug("utils.py ::: add_group_to_inheritance_tree - group_base_node_id = {0}".format(group_base_node_id))
    
    not_main_element = []
    last_main_element = None
    
    while base_node['type'] == 'ou':
        if not base_node['is_main_element'] and base_node['_id'] == str(group_base_node_id):
            break

        if not base_node['is_main_element']:
            not_main_element.append(base_node)
        else:
            last_main_element = base_node
            
        next_base_node = base_node['children'][0]
        
        # Maybe the 'ou' is not the first node, so lets check other nodes
        for child in base_node['children']:
            if child['type'] == 'ou':
                next_base_node = child
                break

        base_node = next_base_node
                
    logger.debug("utils.py ::: add_group_to_inheritance_tree - base_node: type = {0} is_main_element = {1} _id = {2}".format(base_node['type'], base_node['is_main_element'], base_node['_id']))
        
    if base_node['type'] != 'ou' or base_node['is_main_element'] or base_node['_id'] != str(group_base_node_id):
        # Base node not found --> We must create it
        logger.debug("utils.py ::: add_group_to_inheritance_tree - Base node not found --> We must create it")
        
        base_ou = None
        for ou_id in group_path:
            for node in not_main_element:
                if str(node['_id']) == str(ou_id):
                    base_ou = node
                    break
        
        if base_ou is None:
            base_ou = last_main_element
            

        # Get ou from mongoDB
        ou = db.nodes.find_one({'_id': ObjectId(group_base_node_id)})
        if not ou:
            logger.error("utils.py ::: add_group_to_inheritance_tree - OU not found %s" % str(group_base_node_id))
            return False
            
        else:
            # Generate item
            item =  {}
            item['_id'] = str(group_base_node_id)
            item['name'] = ou['name']
            item['type'] = ou['type']
            item['path'] = ou['path']
            item['policies'] = {}
            item['is_main_element'] = False
            item['children'] = []

            base_node = item
            logger.debug("utils.py ::: add_group_to_inheritance_tree - Create %s under %s"%(base_node['name'], base_ou['name']))

            # If inside the base OU is a children that is not a Group
            # we must move that children to the appended OU
            other_node = None
            for child in base_ou['children']:
                if child['type'] != 'group':
                    other_node = child
                    
            if other_node is not None:
                base_ou['children'].remove(other_node)
                base_node['children'].append(other_node)
                logger.debug("utils.py ::: add_group_to_inheritance_tree - Move %s from %s to %s"%(other_node['name'], base_ou['name'], base_node['name']))

            
            base_ou['children'].append(item)
                            
                
                            
    # Add this group to the children
    item =  {}
    item['_id'] = str(group['_id'])
    item['name'] = group['name']
    item['type'] = group['type']
    item['path'] = group['path']
    item['policies'] = {}
        
    item['is_main_element'] = True
    item['children'] = []
    
    base_node['children'].append(item)   
    
    # Sort the groups by alphabetic order
    groups = []
    other_node = None
    for child in base_node['children']:
        if child['type'] == 'group':
            groups.append(child)
            
        else:
            other_node = child
            
    groups.sort(key=lambda x: x['name'], reverse=False)
    
    base_node['children'] = []
    base_node['children'].extend(groups)
    
    if other_node is not None:
        base_node['children'].append(other_node)
                    
    return True
                    
# ------------------------------------------------------------------------------------------------------
def apply_change_in_inheritance(logger, db, action, obj, policy, node, inheritanceTree):
    """Function that looks for the node that received the change (obj) inside the inheritance tree
       and performs the change in its policies.

    Args:
        logger (object): Logger.
        db (object): Mongo DB access object.
        action (str): Could be 'changed' (policy added or changed) or 'deleted' (policy deleted from node).
        obj (object): Node (computer, user, OU or group) that received the change.
        policy (object): Policy that is changed or deleted.
        node (object): Node whose inheritance field must be recalculated.
        inheritanceTree (object): Tree of inheritance objects

    Returns:
        bool: The return value. True for success, False otherwise.

    """
    # Parameter checking
    if logger is None:
        raise ValueError('logger is None')    
        
    if db is None:
        raise ValueError('db is None')    
        
    if action is None:
        raise ValueError('action is None')    

    if not isinstance(action, str):
        raise ValueError('action is not a string')         
        
    if obj is None:
        raise ValueError('obj is None')    
        
    if (not '_id' in obj) or (not 'name' in obj):
        raise ValueError('obj is not a node')           

    if policy is None:
        raise ValueError('policy is None')    

    if (not '_id' in policy) or (not 'targets' in policy):
        raise ValueError('policy is not a policy')          
        
    if node is None:
        raise ValueError('node is None')    
        
    if (not '_id' in node) or (not 'name' in node):
        raise ValueError('node is not a node')           
        
    if inheritanceTree is None:
        raise ValueError('inheritanceTree is None')     
        
    if (not '_id' in inheritanceTree) or (not 'name' in inheritanceTree):
        raise ValueError('inheritanceTree is not a node')           
        
    
    found = False
    this_node = inheritanceTree
    logger.debug("utils.py ::: apply_change_in_inheritance -  this_node['_id'] = {0} obj['_id'] = {1} action={2}".format(this_node['_id'], obj['_id'], action))
        
    if str(this_node['_id']) == str(obj['_id']):
        # This is the object to change
        found = True
        policy_id = str(policy['_id'])
        if action == DELETED_POLICY_ACTION:
            # Remove the policy
            to_remove = None
            for p_id in this_node['policies']:
                if policy_id == p_id:
                    to_remove = p_id
                    break
                    
            if to_remove is None:
                logger.error("utils.py ::: apply_change_in_inheritance - Policy not found %s" % str(policy['_id']))
                return False    
                
            else:
                logger.debug("utils.py ::: apply_change_in_inheritance - Removing policy %s to node %s inherited by %s" % (str(policy['_id']), str(obj['_id']), str(node['_id'])))
                del this_node['policies'][policy_id]
            
        else:
            # Chef if the policy already existed
            existed = False
            for p_id in this_node['policies']:
                if policy_id == p_id:
                    existed = True
                    break
            
            if not existed:
                # Add the policy
                logger.debug("utils.py ::: apply_change_in_inheritance - Adding policy %s to node %s inherited by %s" % (str(policy['_id']), str(obj['_id']), str(node['_id'])))
                this_node['policies'][policy_id] = {}
                this_node['policies'][policy_id]['name'] = policy['name']
                this_node['policies'][policy_id]['name_es'] = policy['name_es']
                this_node['policies'][policy_id]['is_mergeable'] = policy['is_mergeable']      
                this_node['policies'][policy_id]['inherited'] = True

            else:
                logger.debug("utils.py ::: apply_change_in_inheritance - Change in policy %s to node %s inherited by %s" % (str(policy['_id']), str(obj['_id']), str(node['_id'])))
            
        
    else:
        # Continue looking in the tree
        for child in this_node['children']:
            found = (found or apply_change_in_inheritance(logger, db, action, obj, policy, node, child))
            if found:
                break
    
    return found

# ------------------------------------------------------------------------------------------------------
def calculate_initial_inheritance_for_node(logger, db, node):
    """Function that calculates the initial "inheritance" field of a node.

    Args:
        logger (object): Logger.
        db (object): Mongo DB access object.
        node (object): Node whose inheritance field must be recalculated.

    Returns:
        bool: The return value. True for success, False otherwise.

    """
    
    # Parameter checking
    if logger is None:
        raise ValueError('logger is None')    
        
    if db is None:
        raise ValueError('db is None')    
        
    if node is None:
        raise ValueError('node is None')    
        
    if (not '_id' in node) or (not 'name' in node):
        raise ValueError('node is not a node')          
        
    if (not 'inheritance' in node) or not node['inheritance']:
        if node['type'] == 'group':
            # Group (does not inherit anything)
            
            # Add current node
            item =  {}
            item['_id'] = str(node['_id'])
            item['name'] = node['name']
            item['path'] = node['path']
            item['type'] = node['type']
            item['policies'] = {}
                
            item['is_main_element'] = True
            item['children'] = []
            
            inheritanceTree = item
            
        else:
            # OU, user or computer
            inheritanceTree = None
            previousOU = None
            for ou_id in node.get('path').split(','):
                if ou_id != 'root':
                    # Get ou from mongoDB
                    ou = db.nodes.find_one({'_id': ObjectId(ou_id)})
                    if not ou:
                        logger.error("utils.py ::: calculate_initial_inheritance_for_node - OU not found %s" % str(ou_id))
                        return False
                        
                    else:
                        # Generate item
                        item =  {}
                        item['_id'] = str(ou_id)
                        item['name'] = ou['name']
                        item['type'] = ou['type']
                        item['path'] = ou['path']
                        item['policies'] = {}
                        item['is_main_element'] = True
                        item['children'] = []
                        
                        if inheritanceTree is None:
                            inheritanceTree = item
                        
                        if previousOU is not None:
                            previousOU['children'].append(item)
                        
                        previousOU = item
            
            if previousOU is None:
                if 'root' != node.get('path'):
                    logger.error("utils.py ::: calculate_initial_inheritance_for_node - OUs not found for path %s" % str(node.get('path')))
                return False
        
            if 'memberof' in node:
                # Add the groups in order (depth and aphabetic)
                groups_ids = [ObjectId(group_id) for group_id in node['memberof']]
                groups = [group for group in db.nodes.find({'_id': {'$in': groups_ids}}).sort([('name',1)])]
                groups.sort(key=lambda x: x['path'].count(','), reverse=False)
                
                for group in groups:
                    group_ou_id = group['path'].split(',')[-1]
                    if previousOU['_id'] != group_ou_id:
                        # Get ou from mongoDB
                        ou = db.nodes.find_one({'_id': ObjectId(group_ou_id)})
                        if not ou:
                            logger.error("utils.py ::: calculate_initial_inheritance_for_node - OU not found %s" % str(group_ou_id))
                            return False
                            
                        else:
                            # Generate item
                            item =  {}
                            item['_id'] = str(group_ou_id)
                            item['name'] = ou['name']
                            item['type'] = ou['type']
                            item['path'] = ou['path']
                            item['policies'] = {}
                            item['is_main_element'] = False
                            item['children'] = []
                            
                            previousOU['children'].append(item)
                            previousOU = item
                            
                            
                    # Add this group to the children
                    item =  {}
                    item['_id'] = str(group['_id'])
                    item['name'] = group['name']
                    item['type'] = group['type']
                    item['path'] = group['path']
                    item['policies'] = {}
                        
                    item['is_main_element'] = True
                    item['children'] = []
                    
                    previousOU['children'].append(item)   
        
            # Add current node
            item =  {}
            item['_id'] = str(node['_id'])
            item['name'] = node['name']
            item['path'] = node['path']
            item['type'] = node['type']
            item['policies'] = {}
                
            item['is_main_element'] = True
            item['children'] = []
            
            previousOU['children'].append(item)   
    
        node['inheritance'] = inheritanceTree

    return True
    
# ------------------------------------------------------------------------------------------------------
def recalculate_inherited_field(logger, db, obj_id):
    """Function that recalculate the "inheritance" field of a node.

    Args:
        logger (object): Logger.
        db (object): Mongo DB access object.
        obj_id (string): ID of the node.

    Returns:
        bool: The return value. True for success, False otherwise.

    """
    # Parameter checking
    if logger is None:
        raise ValueError('logger is None')    
        
    if db is None:
        raise ValueError('db is None')    
        
    if obj_id is None:
        raise ValueError('obj_id is None')  

    if not isinstance(obj_id, str):
        raise ValueError('obj_id is not a string')      
        
    
    obj = db.nodes.find_one({'_id': ObjectId(obj_id)})
    if not obj:
        logger.error("utils.py ::: recalculate_inherited_field - Node not found %s" % str(obj_id))
        return False    

    inherited_updated = False
    
    for policy in get_inheritance_tree_policies_list(obj['inheritance'], []):
        if not policy['is_mergeable']:
            # Set the 'inherited' field to false in all nodes except one
            node_list = get_inheritance_tree_node_list(obj['inheritance'], str(policy['_id']))
            priority_node = get_priority_node(db, node_list)
            set_inherited_field(logger, obj['inheritance'], str(policy['_id']), node_list, str(priority_node)) 
            inherited_updated = True

    if inherited_updated:
        # Update node in mongo db to save the 'inherited' field
        db.nodes.update({'_id': obj['_id']}, {'$set':{'inheritance': obj['inheritance']}})
    
    return obj['inheritance']
    
    
# ------------------------------------------------------------------------------------------------------
def recalculate_inheritance_for_node(logger, db, action, obj, policy, node):
    """Function that recalculate the "inheritance" field of a node by changing or deleting a policy in
    a related node.

    Args:
        logger (object): Logger.
        db (object): Mongo DB access object.
        action (str): Could be 'changed' (policy added or changed) or 'deleted' (policy deleted from node), or 'created' (a object is created with policies when is moved).
        obj (object): Node (computer, user, OU or group) that received the change.
        policy (object): Policy that is changed or deleted.
        node (object): Node whose inheritance field must be recalculated.

    Returns:
        bool: The return value. True for success, False otherwise.

    """
    # Parameter checking
    if logger is None:
        raise ValueError('logger is None')    
        
    if db is None:
        raise ValueError('db is None')    
        
    if action is None:
        raise ValueError('action is None')  

    if not isinstance(action, str):
        raise ValueError('action is not a string')         
    
    if obj is None:
        raise ValueError('obj is None')  

    if (not '_id' in obj) or (not 'name' in obj):
        raise ValueError('obj is not a node')          
        
    if policy is None:
        raise ValueError('policy is None')  

    if (not '_id' in policy) or (not 'targets' in policy):
        raise ValueError('policy is not a policy')          
        
    if node is None:
        raise ValueError('node is None')          
    
    if (not '_id' in node) or (not 'name' in node):
        raise ValueError('node is not a node')      
    
    # Check if the policy is applicable to this object
    if not node['type'] in policy['targets']:
        return False
    
    # Calculate inheritance tree for the first time when neccessary
    if not calculate_initial_inheritance_for_node(logger, db, node):
        return False
        
    if action == 'created':
        # The object is being moved to a new position in the nodes tree
        move_in_inheritance(logger, db, obj, node['inheritance'])
        
        
        
    # Look for the node of the inheritance tree that changes
    # and apply the change to that node propagating it when neccessary
    success = apply_change_in_inheritance(logger, db, action, obj, policy, node, node['inheritance'])
    
    if success:
        if not policy['is_mergeable']:
            # Set the 'inherited' field to false in all nodes except one
            logger.debug("utils.py ::: recalculate_inheritance_for_node - policy_id: {0}".format(str(policy['_id'])))
            node_list = get_inheritance_tree_node_list(node['inheritance'], str(policy['_id']))
            logger.debug("utils.py ::: recalculate_inheritance_for_node - node_list: {0}".format(node_list))
            priority_node = get_priority_node(db, node_list)
                
            logger.debug("utils.py ::: recalculate_inheritance_for_node - priority object: %s" % str(priority_node))
            logger.debug("utils.py ::: recalculate_inheritance_for_node - inheritance: {0}".format(node['inheritance']))
            set_inherited_field(logger, node['inheritance'], str(policy['_id']), node_list, str(priority_node))
    
        # Update node in mongo db
        db.nodes.update({'_id': node['_id']}, {'$set':{'inheritance': node['inheritance']}})
    
    return success
                        
# ------------------------------------------------------------------------------------------------------
# To remove all inheritance information from database:
#   db.nodes.update({"inheritance": { $exists: true }}, { $unset: { "inheritance": {$exist: true } }}, {multi: 1})
def trace_inheritance(logger, db, action, obj, policy):
    """Function that fills or complete the "inheritance" field of a mongo db node.

    The "inheritance" field must include the neccessary information about the inheritance of policies
    in that node. That information includes all the intermediate nodes (OUs and groups) and policies
    applied to them.

    Args:
        logger (object): Logger.
        db (object): Mongo DB access object.
        action (str): Could be 'changed' (policy added or changed) or 'deleted' (policy deleted from node), or 'created' (a object is created with policies when is moved).
        obj (object): Node (computer, user, OU or group) that received the change.
        policy (object): Policy that is changed or deleted.

    Returns:
        bool: The return value. True for success, False otherwise.

    """
    
    # Parameter checking
    if logger is None:
        raise ValueError('logger is None')    
        
    if db is None:
        raise ValueError('db is None')    
        
    if action is None:
        raise ValueError('action is None')  

    if not isinstance(action, str):
        raise ValueError('action is not a string')         
    
    if obj is None:
        raise ValueError('obj is None')  

    if (not '_id' in obj) or (not 'name' in obj):
        raise ValueError('obj is not a node')  
        
    if policy is None:
        raise ValueError('policy is None')  
    
    if (not '_id' in policy) or (not 'targets' in policy):
        raise ValueError('policy is not a policy')  
    
    logger.debug("utils.py ::: trace_inheritance - action: {0} obj: {1} policy: {2}".format(action, obj['name'], policy['_id']))

    # First lets calculate all the nodes that are affected by this change
    affected_nodes = []
    policyId = unicode(policy['_id'])
    logger.info("utils.py ::: trace_inheritance - policyId = {0}".format(policyId))
    
    if obj['type'] == 'ou':
        # If a policy is changed in an OU this change will affect other OUs, users and computers
        # but not groups (and to itself)
        targets = policy['targets']
        targets.remove('group')
        logger.info("utils.py ::: trace_inheritance - obj is OU = {0}".format(obj['name']))
        affected_nodes = list(db.nodes.find({'path': {'$regex': '.*' + unicode(obj['_id']) + '.*'}, 
                                    'type':{'$in': targets}}))
        affected_nodes.append(obj)
             
    elif obj['type'] == 'group':
        logger.debug("utils.py ::: trace_inheritance - obj is GROUP = {0}".format(obj['name']))
        targets = policy['targets']
        # If a policy is changed in an Group this change will affect to his members (and to itself)
        affected_nodes = list(db.nodes.find( {'_id'  : {'$in': obj.get('members', [])}, 'type':{'$in': targets}} ))
        affected_nodes.append(obj)

    elif obj['type'] == 'computer':
        # If a policy is changed in a Computer this change will affect only to itself
        logger.debug("utils.py ::: trace_inheritance - obj is COMPUTER = {0}".format(obj['name']))
        affected_nodes.append(obj)
        
    elif obj['type'] == 'user':
        # If a policy is changed in a User this change will affect only to itself
        logger.debug("utils.py ::: trace_inheritance - obj is USER = {0}".format(obj['name']))
        affected_nodes.append(obj)        
    
    else:
        logger.error("utils.py ::: trace_inheritance - Bad node type = {0} for node = {1}".format(obj['type'], obj['_id']))
        return False

    success = True
    for node in affected_nodes:
        logger.debug("utils.py ::: trace_inheritance - affected_node = {0} - {1}".format(node['name'], node['type']))
        success = (success and recalculate_inheritance_for_node(logger, db, action, obj, policy, node))
        logger.debug("utils.py ::: trace_inheritance - success = {0}".format(success))

    return success


def getNextUpdateSeq(db):  
    ''' Return next four digit sequence of an update

    Args:
      db (object):    database connection
    '''

    cursor = db.updates.find({'name':{'$regex':SERIALIZED_UPDATE_PATTERN}},
                             {'_id':1}).sort('_id',-1).limit(1)

    if cursor.count() == 0:
        nseq = '0000'
    else:
        latest = int(cursor.next().get('_id'))
        nseq = "%04d" % (latest+1)

    logger.debug("utils.py ::: getNextUpdateSeq - nseq = %s" % nseq)

    return nseq

def is_cli_request():
    return os.environ.get('CLI_REQUEST') == 'True'


def has_cli_permission(code, name):
    assert SCRIPTCODES[name] == code, _('No permission to execute this function from script')
    
def mongodb_backup(path=None, collection=None):
    ''' Back up of mongo collection or database
    
    Args:
      path(str):        backup directory where hold files
      collection(str):  mongo collection for backing up. If is None, then all database is backed up.
    '''
    logger.info("Backing up mongodb ...")
    exitstatus = 0

    try:

        settings = get_current_registry().settings

        if is_cli_request():
            has_cli_permission(os.environ['SCRIPT_CODE'], mongodb_backup.__name__)
            path = os.environ['BACKUP_DIR']

        logger.debug("utils.py ::: mongodb_backup - path = %s" % path)
        logger.debug("utils.py ::: mongodb_backup - collection = %s" % collection)

        assert path is not None, _('Missing required arguments')

        if not os.path.exists(path):
            os.mkdir(path)

        mongodb = settings['mongodb']
       
        exitstatus = mongodb.dump(path, collection)
        logger.info("mongodb backup ended.")

    except AssertionError, msg:
        logger.warning(msg)
        exitstatus = 1

    return exitstatus

def mongodb_restore(path=None, collection=None):
    ''' Restore of mongo collection or database
    
    Args:
      path(str):        directory where backup files are.
      collection(str):  mongo collection for restoring. If is None, then all database is restored.
    '''
    logger.info("Restoring mongodb ...")

    try:

        settings = get_current_registry().settings

        if is_cli_request():
            has_cli_permission(os.environ['SCRIPT_CODE'], mongodb_restore.__name__)
            path = os.environ['BACKUP_DIR']

        logger.debug("utils.py ::: mongodb_restore - path = %s" % path)
        logger.debug("utils.py ::: mongodb_restore - collection = %s" % collection)

        assert path is not None, _('Missing required arguments')
        assert os.path.exists(path), _('Directory %s can\'t be found.') % path

        mongodb = settings['mongodb']

        exitstatus = mongodb.restore(path, collection)
        logger.info("mongodb restored from backup.")

    except AssertionError, msg:
        logger.warning(msg)
        exitstatus = 1

    return exitstatus
 

def upload_cookbook(user=None,cookbook_path=None):
    ''' Upload cookbook to chef server
    
    Args:
      user(str):            user with permission for uploading cookbook to chef server
      cookbook_path(str):   path to cookbook files
    '''
    logger.info("Uploading cookbook ...")
    exitstatus = 0

    try:

        settings = get_current_registry().settings

        if is_cli_request():
            has_cli_permission(os.environ['SCRIPT_CODE'], upload_cookbook.__name__)
            user = {'username': os.environ['GECOS_USER']}
            cookbook_path = os.environ['COOKBOOK_DIR']

        assert user is not None and cookbook_path is not None, _('Missing required arguments')
        assert os.path.isdir(cookbook_path), _('Directory %s can\'t be found.') % cookbook_path

        admin_cert = os.sep.join([settings.get('firstboot_api.media'), user['username'], 'chef_user.pem'])
        logger.debug("upload_cookbook: admin_cert = %s" % admin_cert)

        chef_url = settings.get('chef.url') + '/organizations/default'
        logger.debug("upload_cookbook: chef_url = %s" % chef_url)

        command = 'knife cookbook upload {0} -s {1} -u {2} -k {3} -o {4}'.format(settings['chef.cookbook_name'], chef_url, user['username'], admin_cert, cookbook_path)

        upload_output = subprocess.check_output(command, shell=True)
        logger.info(upload_output)
        logger.info("Uploaded cookbook.")
        
    except AssertionError, msg:
        logger.warning(msg)
        exitstatus = 1

    except subprocess.CalledProcessError, msg:
        logger.error(msg.cmd)
        logger.error(msg.output)
        exitstatus = msg.returncode

    return exitstatus


def chefserver_backup(backupdir=None):
    ''' Backing up all Chef server data
    
    Args:
      username(str):    user with permission in chef server
      backupdir(str):   backup directory where hold files
    '''
    logger.info("Backing up Chef Server ...")
    exitstatus = 0

    try:
 
        settings = get_current_registry().settings

        if is_cli_request():
            has_cli_permission(os.environ['SCRIPT_CODE'], chefserver_backup.__name__)
            backupdir = os.environ['BACKUP_DIR']

        logger.debug("utils.py ::: chefserver_backup - backupdir = %s" % backupdir)

        assert backupdir is not None, _('Missing required arguments')

        if not os.path.exists(backupdir):
            os.mkdir(backupdir)

        command = '{0} {1} {2}'.format(settings['updates.chef_backup'], backupdir, settings.get('chef.url'))
        backup_output = subprocess.check_output(command, shell=True)
        logger.info(backup_output)
        logger.info("Chef Server backup ended.")

    except AssertionError, msg:
        logger.error(msg)
        exitstatus = 1

    except subprocess.CalledProcessError, msg:
        logger.error(msg.cmd)
        logger.error(msg.output)
        exitstatus = msg.returncode

    return exitstatus

def chefserver_restore(backupdir=None):
    ''' Restoring Chef server data from a backup that was created by the chefserver_backup function
    
    Args:
      username(str):    user with permission in chef server
      backupdir(str):   directory where backup files are
    '''
    logger.info("Restoring Chef Server ...")
    exitstatus = 0

    try:

        settings = get_current_registry().settings

        if is_cli_request():
            has_cli_permission(os.environ['SCRIPT_CODE'], chefserver_restore.__name__)
            backupdir = os.environ['BACKUP_DIR']

        logger.debug("utils.py ::: chefserver_backup - backupdir = %s" % backupdir)

        assert backupdir is not None, _('Missing required arguments')

        if not os.path.exists(backupdir):
            os.mkdir(backupdir)

        command = '{0} {1} {2}'.format(settings['updates.chef_restore'], backupdir, settings.get('chef.url'))
        restore_output = subprocess.check_output(command, shell=True)
        logger.info(restore_output)
        logger.info("Chef Server restore ended.")

    except AssertionError, msg:
        logger.warning(msg)
        exitstatus = 1

    except subprocess.CalledProcessError, msg:
        logger.error(msg.cmd)
        logger.error(msg.output)
        exitstatus = msg.returncode

    return exitstatus
     

def import_policies(username=None, inifile=None):
    ''' Import policies from Chef Server to mongo database
    
    Args:
      username(str):    user with permission in chef server
      inifile(str):     path to gecoscc.ini
    '''
    from gecoscc.commands.import_policies import Command as ImportPoliciesCommand

    logger.info("Importing policies ...")
 
    try:

        settings = get_current_registry().settings

        if is_cli_request():
            has_cli_permission(os.environ['SCRIPT_CODE'], import_policies.__name__)
            inifile = os.environ['CONFIG_URI']
            username = os.environ['GECOS_USER']

        logger.debug("utils.py ::: import_policies - inifile = %s" % inifile)
        logger.debug("utils.py ::: import_policies - username = %s" % username)

        admin_cert = os.sep.join([settings.get('firstboot_api.media'), username, 'chef_user.pem'])
        logger.debug("utils.py ::: import_policies - admin_cert = %s" % admin_cert)

        argv_bc = sys.argv
        sys.argv = ['pmanage', inifile, 'import_policies', '-a', username, '-k', admin_cert]
        command = ImportPoliciesCommand(inifile)
        command.command()
        sys.argv = argv_bc

        logger.info("Imported policies.")

    except AssertionError, msg:
        logger.warning(msg)

def auditlog(request, action=None):
    ''' Tracking user temporal information 
    
    Args:
        request(object): Pyramid request 
        action(str):     user action (login,logout,expire, ...)
        
    '''
    logger.debug("utils.py ::: auditlog - request = {}".format(request))
    logger.debug("utils.py ::: auditlog - action = {}".format(action))
    if not action or action not in AUDIT_ACTIONS:
        logger.error("utils.py ::: auditlog - unrecognized action = {}".format(action))
    else:

        try:
            logger.debug("utils.py ::: auditlog - request.user = {}".format(request.user))
            if action == 'login':
                username = request.POST.get('username')
            else:
                # Logout or expired
                if request.user is None:
                    logger.warn('utils.py ::: auditlog: there is no user data in session (¿logout after session expired?)')
                    return                     
                
                try:
                    username = request.user['username']
                except Exception as e:
                    logger.warn('utils.py ::: auditlog: error getting user session data: %s'%(str(e)))
                    return
                
                
            logger.debug("utils.py ::: auditlog - username = {}".format(username))
            ipaddr = request.headers.get('X-Forwarded-For', request.remote_addr)
            logger.debug("utils.py ::: auditlog - ipaddr = {}".format(ipaddr))
            agent = request.user_agent
            logger.debug("utils.py ::: auditlog - agent = {}".format(agent))

            request.db.auditlog.insert({
                'username': username, 
                'action': action,
                'ipaddr': ipaddr, 
                'user-agent': agent, 
                'timestamp': int(time.time())
            })

        except (KeyError, Exception):
             logger.error(traceback.format_exc())




