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

from bson import ObjectId, json_util
from copy import deepcopy

from chef import ChefAPI, Client
from chef import Node as ChefNode
from chef.exceptions import ChefError
from chef.node import NodeAttributes

from pyramid.threadlocal import get_current_registry

RESOURCES_RECEPTOR_TYPES = ('computer', 'ou', 'user', 'group')
RESOURCES_EMITTERS_TYPES = ('printer', 'storage', 'repository')
POLICY_EMITTER_SUBFIX = '_can_view'
USER_MGMT = 'users_mgmt'
SOURCE_DEFAULT = MASTER_DEFAULT = 'gecos'
USE_NODE = 'use_node'


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
    chef_client_pem = get_pem_path_for_username(settings, username, 'chef_client.pem')
    chef_user_pem = get_pem_path_for_username(settings, username, 'chef_user.pem')
    if os.path.exists(chef_client_pem):
        chef_pem = chef_client_pem
    else:
        chef_pem = chef_user_pem
    api = _get_chef_api(chef_url, username, chef_pem)
    return api


def _get_chef_api(chef_url, username, chef_pem):
    if not os.path.exists(chef_pem):
        raise ChefError('User has no pem to access chef server')
    api = ChefAPI(chef_url, chef_pem, username)
    return api


def create_chef_admin_user(api, settings, usrname, password=None):
    username = toChefUsername(usrname)
    if password is None:
        password = password_generator()
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


def remove_chef_computer_data(computer, api):
    node_chef_id = computer.get('node_chef_id', None)
    if node_chef_id:
        node = reserve_node_or_raise(node_chef_id, api, 'gcc-remove-computer-data-%s' % random.random())
        if node:
            settings = get_current_registry().settings
            cookbook_name = settings.get('chef.cookbook_name')
            cookbook = node.normal.get(cookbook_name)
            for mgmt in cookbook:
                if mgmt == USER_MGMT:
                    continue
                cookbook.pop(mgmt)
            save_node_and_free(node)


def remove_chef_user_data(user, computers, api):
    settings = get_current_registry().settings
    cookbook_name = settings.get('chef.cookbook_name')
    for computer in computers:
        node_chef_id = computer.get('node_chef_id', None)
        if node_chef_id:
            node = reserve_node_or_raise(node_chef_id, api, 'gcc-remove-user-data-%s' % random.random())
            if node:
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
    settings = get_current_registry().settings
    seconds_block_is_busy = int(settings.get('chef.seconds_block_is_busy'))
    time_to_exp = datetime.timedelta(seconds=seconds_block_is_busy)
    node = ChefNode(node_id, api)
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
                is_visible = db.nodes.find_one(
                    {'_id': ObjectId(object_related_id),
                     'path': get_filter_nodes_parents_ou(db,
                                                         ou_id,
                                                         obj_id)})
                if is_visible:
                    object_related_visible.append(object_related_id)
            if object_related_list != object_related_visible:
                if object_related_visible:
                    policies[unicode(emitter_policy_id)]['object_related_list'] = object_related_visible
                else:
                    del policies[unicode(emitter_policy_id)]
                have_updated = True
    if have_updated:
        db.nodes.update({'_id': obj_id}, {'$set': {'policies': policies}})
        obj = db.nodes.find_one({'_id': obj_id})
    return obj


def apply_policies_to_computer(nodes_collection, computer, auth_user, api=None, initialize=False):
    from gecoscc.tasks import object_changed, object_created
    if api and initialize:
        computer = visibility_group(nodes_collection.database, computer)
        computer = visibility_object_related(nodes_collection.database, computer)
        remove_chef_computer_data(computer, api)

    ous = nodes_collection.find(get_filter_ous_from_path(computer['path']))
    for ou in ous:
        if ou.get('policies', {}):
            object_changed.delay(auth_user, 'ou', ou, {}, computers=[computer])

    groups = nodes_collection.find({'_id': {'$in': computer.get('memberof', [])}})
    for group in groups:
        if group.get('policies', {}):
            object_changed.delay(auth_user, 'group', group, {}, computers=[computer])

    object_created.delay(auth_user, 'computer', computer, computers=[computer])


def apply_policies_to_user(nodes_collection, user, auth_user, api=None, initialize=False):
    from gecoscc.tasks import object_changed, object_created

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
            object_changed.delay(auth_user, 'ou', ou, {}, computers=computers)

    groups = nodes_collection.find({'_id': {'$in': user.get('memberof', [])}})
    for group in groups:
        if group.get('policies', {}):
            object_changed.delay(auth_user, 'group', group, {}, computers=computers)

    object_created.delay(auth_user, 'user', user, computers=computers)


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
#
def toChefUsername(username):
    return username.replace('.', '___')

# Transforms back a Chef username into a regular username
# by replacing the "___" by dots
#
def fromChefUsername(username):
    return username.replace('___', '.')

# Get the components of a URL
#
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
