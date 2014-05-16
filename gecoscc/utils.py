import os
from chef import ChefAPI, Client
from chef import Node as ChefNode
from chef.exceptions import ChefError


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


def get_filter_nodes_belonging_ou(ou_id):
    if ou_id == 'root':
        return {'$regex': '%s.*' % ou_id}
    return {'$regex': '.*,%s.*' % ou_id}


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
        update_node(api, node_id, ou, collection_nodes)
    return register_node(api, node_id, ou, collection_nodes)