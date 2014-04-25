import os
from chef import ChefAPI
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


def get_chef_api(settings, user):
    username = user['username']
    url = user.get('variables', {}).get('chef_server_uri', None) or settings.get('chef.url')
    chef_client_pem = get_pem_path_for_username(settings, user['username'], 'chef_client.pem')
    chef_user_pem = get_pem_path_for_username(settings, user['username'], 'chef_user.pem')
    if os.path.exists(chef_client_pem):
        api = ChefAPI(url, chef_client_pem, username)
    elif os.path.exists(chef_user_pem):
        api = ChefAPI(url, chef_user_pem, username)
    else:
        raise ChefError('User has no pem to access chef server')
    return api


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
