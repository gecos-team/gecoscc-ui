import os
from chef import ChefAPI, Client
from chef.exceptions import ChefError


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

# Chef utils


def get_chef_api(settings, user):
    username = user['username']
    chef_url = user.get('variables', {}).get('chef_server_uri', None) or settings.get('chef.url')
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

    