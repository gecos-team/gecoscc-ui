import os

from bson import ObjectId

from chef import ChefAPI, Client
from chef import Node as ChefNode
from chef.exceptions import ChefError

from pyramid.threadlocal import get_current_registry

RESOURCES_RECEPTOR_TYPES = ('computer', 'ou', 'user', 'group')
RESOURCES_EMITTERS_TYPES = ('printer', 'storage', 'repository')
POLICY_EMITTER_SUBFIX = '_can_view'


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

# Chef utils


def get_chef_api(settings, user):
    username = user['username']
    chef_url = settings.get('chef.url')
    chef_client_pem = get_pem_path_for_username(settings, user['username'], 'chef_client.pem')
    chef_user_pem = get_pem_path_for_username(settings, user['username'], 'chef_user.pem')
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


def create_chef_admin_user(api, settings, username, password):
    data = {'name': username, 'password': password, 'admin': True}
    chef_user = api.api_request('POST', '/users', data=data)
    user_private_key = chef_user.get('private_key', None)
    if user_private_key:
        save_pem_for_username(settings, username, 'chef_user.pem', user_private_key)
    chef_client = Client.create(name=username, api=api, admin=True)
    client_private_key = getattr(chef_client, 'private_key', None)
    if client_private_key:
        save_pem_for_username(settings, username, 'chef_client.pem', client_private_key)


def delete_chef_admin_user(api, settings, username):
    try:
        api.api_request('DELETE', '/users/%s/' % username)
        api.api_request('DELETE', '/clients/%s/' % username)
        return True
    except:
        return False


def remove_chef_computer_data(computer, api):
    node_chef_id = computer.get('node_chef_id', None)
    if node_chef_id:
        node = ChefNode(node_chef_id, api)
        if node:
            settings = get_current_registry().settings
            cookbook_name = settings.get('chef.cookbook_name')
            node.normal.get(cookbook_name).clear()
            node.save()


def remove_chef_user_data(user, computers, api):
    settings = get_current_registry().settings
    cookbook_name = settings.get('chef.cookbook_name')
    for computer in computers:
        node_chef_id = computer.get('node_chef_id', None)
        if node_chef_id:
            node = ChefNode(node_chef_id, api)
        if node:
            try:
                user_mgmt = node.normal.get_dotted('%s.%s' % (cookbook_name, 'users_mgmt'))
                for policy in user_mgmt:
                    try:
                        user_mgmt.get(policy).get('users').pop(user['name'])
                    except (KeyError, AttributeError):
                        continue
                node.save()
            except KeyError:
                pass


def apply_policies_to_computer(nodes_collection, computer, auth_user, api=None, initialize=False):
    from gecoscc.tasks import object_changed, object_created

    if api and initialize:
        remove_chef_computer_data(computer, api)

    ous = nodes_collection.find(get_filter_ous_from_path(computer['path']))
    for ou in ous:
        object_changed.delay(auth_user, 'ou', ou, {}, computers=[computer])

    groups = nodes_collection.find({'_id': {'$in': computer.get('memberof', [])}})
    for group in groups:
        object_changed.delay(auth_user, 'group', group, {}, computers=[computer])

    object_created.delay(auth_user, 'computer', computer, computers=[computer])


def apply_policies_to_user(nodes_collection, user, auth_user, api, initialize=False):
    from gecoscc.tasks import object_changed, object_created

    computers = get_computer_of_user(nodes_collection, user)
    if not computers:
        return

    if api and initialize:
        remove_chef_user_data(user, computers, api)

    ous = nodes_collection.find(get_filter_ous_from_path(user['path']))
    for ou in ous:
        object_changed.delay(auth_user, 'ou', ou, {}, computers=computers)

    groups = nodes_collection.find({'_id': {'$in': user.get('memberof', [])}})
    for group in groups:
        object_changed.delay(auth_user, 'group', group, {}, computers=computers)

    object_created.delay(auth_user, 'user', user, computers=computers)


def get_pem_for_username(settings, username, pem_name):
    return open(get_pem_path_for_username(settings, username, pem_name), 'r').read().encode('base64')


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
    node = ChefNode(node_id, api)
    if not node.attributes.to_dict():
        return False
    try:
        computer_name = node.attributes.get_dotted('ohai_gecos.pclabel')
    except KeyError:
        computer_name = node_id
    node_id = collection_nodes.insert({'path': '%s,%s' % (ou['path'], unicode(ou['_id'])),
                                       'name': computer_name,
                                       'type': 'computer',
                                       'lock': False,
                                       'source': 'gecos',
                                       'memberof': [],
                                       'policies': {},
                                       'registry': '',
                                       'family': 'desktop',
                                       'node_chef_id': node_id})
    return node_id


def update_node(api, node_id, ou, collection_nodes):
    node = ChefNode(node_id, api)
    if not node.attributes.to_dict():
        return False
    try:
        computer_name = node.attributes.get_dotted('ohai_gecos.pclabel')
    except KeyError:
        computer_name = node_id
    node_id = collection_nodes.update({'node_chef_id': node_id},
                                      {'path': '%s,%s' % (ou['path'], unicode(ou['_id'])),
                                       'name': computer_name,
                                       'type': 'computer',
                                       'lock': False,
                                       'source': 'gecos',
                                       'memberof': [],
                                       'policies': {},
                                       'registry': '',
                                       'family': 'desktop',
                                       'node_chef_id': node_id})
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


def get_filter_in_domain(node):
    path_domain = get_domain_path(node)
    return {'$regex': '^%s' % ','.join(path_domain)}