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

import crypt

from copy import deepcopy

EXCLUDE_GENERIC_ATTRS = ['job_ids', 'updated_by', 'support_os']


# Local user rules

def encrypt_password(objs_ui, obj, node, field_chef, **kwargs):
    field_ui = field_chef.split('.')[-1]
    sha_512_code = "$6$"
    users = deepcopy(objs_ui.get(field_ui, []))
    for user in users:
        if 'password' in user:
            user['password'] = crypt.crypt(user['password'], sha_512_code)
            
    return users


rules_localusers_res_path = 'gecos_ws_mgmt.misc_mgmt.local_users_res'

RULES_LOCAL_USERS_RES = {'gecos_ws_mgmt.misc_mgmt.local_users_res.users_list': encrypt_password}

# end local user rules


# Emitter policies

EMITTER_OBJECT_RULES = {
    'printer': ('name', 'manufacturer', 'model', 'uri', 'ppd_uri', 'oppolicy'),
    'repository': {'repo_name': 'name',
                   'uri': 'uri',
                   'components': 'components',
                   'distribution': 'distribution',
                   'deb_src': 'deb_src',
                   'repo_key': 'repo_key',
                   'key_server': 'key_server'},
    'storage': ('name', 'uri'),
    'software_profile': 'packages',
}


def get_object_related(obj_related, attrs=None):
    if attrs is None:
        attrs = EMITTER_OBJECT_RULES.get(obj_related['type'])
    obj = {}
    if isinstance(attrs, tuple):
        for attr in attrs:
            if obj_related[attr] == '':
                continue
            obj[attr] = obj_related[attr]
    elif isinstance(attrs, dict):
        for obj_attr, obj_ui_attr in attrs.items():
            if obj_related[obj_ui_attr] == '':
                continue
            obj[obj_attr] = obj_related[obj_ui_attr]
    elif isinstance(attrs, basestring):
        obj = obj_related[attrs]
    return obj


def object_related_list(objs_ui, **kwargs):
    objs = []
    if objs_ui:
        attrs = EMITTER_OBJECT_RULES.get(objs_ui['type'])
        for obj_ui in objs_ui['object_related_list']:
            if obj_ui['type'] == 'software_profile':
                objs.extend(get_object_related(obj_ui, attrs))
            else:
                objs.append(get_object_related(obj_ui, attrs))
    return objs


def object_related_list_reverse(obj_emiter, obj, node, field_chef, **kwargs):
    objects_related = deepcopy(node.attributes.get_dotted(field_chef))
    new_object_related = get_object_related(obj_emiter)
    obj_type = obj_emiter['type']
    if isinstance(EMITTER_OBJECT_RULES[obj_type], tuple):
        field_pk = 'name'
    else:
        inv_rules = dict(zip(EMITTER_OBJECT_RULES[obj_type].values(),
                             EMITTER_OBJECT_RULES[obj_type].keys()))
        field_pk = inv_rules['name']
    for i, object_related in enumerate(objects_related):
        if new_object_related[field_pk] == object_related[field_pk]:
            objects_related[i] = new_object_related
            break
    return objects_related


def storage_related_reverse(obj_emiter, obj, node, field_chef, **kwargs):
    objects_related = deepcopy(node.attributes.get_dotted(field_chef))
    new_object_related = get_object_related(obj_emiter)
    obj_type = obj_emiter['type']
    if isinstance(EMITTER_OBJECT_RULES[obj_type], tuple):
        field_pk = 'name'
    else:
        inv_rules = dict(zip(EMITTER_OBJECT_RULES[obj_type].values(),
                             EMITTER_OBJECT_RULES[obj_type].keys()))
        field_pk = inv_rules['name']
    for username, object_related in objects_related.items():
        for i, storage in enumerate(object_related.get('gtkbookmarks', [])):
            if new_object_related[field_pk] == storage[field_pk]:
                object_related['gtkbookmarks'][i] = new_object_related
                break
    return objects_related.to_dict()


def storage_related(objs_ui, obj, node, field_chef, **kwargs):
    user_storage = object_related_list(objs_ui, obj=obj, node=node, field_chef=field_chef, **kwargs)
    return users_list({'gtkbookmarks': user_storage}, obj=obj,  node=node, field_chef=field_chef, *kwargs)

# Printer can view
RULES_PRINTER_CAN_VIEW_RES = {'gecos_ws_mgmt.printers_mgmt.printers_res.printers_list': object_related_list}

# Software can view
RULES_SOFTWARE_CAN_VIEW_RES = {'gecos_ws_mgmt.software_mgmt.software_sources_res.repo_list': object_related_list}

# Storage can view
RULES_STORAGE_CAN_VIEW_RES = {'gecos_ws_mgmt.users_mgmt.user_shared_folders_res.users': storage_related}

RULES_PRINTER_CAN_VIEW_REVERSE_RES = {'gecos_ws_mgmt.printers_mgmt.printers_res.printers_list': object_related_list_reverse}

# Software can view
RULES_SOFTWARE_CAN_VIEW_REVERSE_RES = {'gecos_ws_mgmt.software_mgmt.software_sources_res.repo_list': object_related_list_reverse}

# Storage can view
RULES_STORAGE_CAN_VIEW_REVERSE_RES = {'gecos_ws_mgmt.users_mgmt.user_shared_folders_res.users': storage_related_reverse}

# Software profiles res
RULES_SOFTWARE_PROFILE_RES = {'gecos_ws_mgmt.software_mgmt.package_profile_res.package_list': object_related_list}

# End emitter policies


# User policies

def get_username_chef_format(user):
    return user['name'].replace('.', '###')


def users_list(obj_ui, obj, node, field_chef, *kwargs):
    users = deepcopy(node.attributes.get_dotted(field_chef))
    if not users:
        users = {}
    else:
        users = users.to_dict()
    username = get_username_chef_format(obj)
    if username in users:
        node_obj = users[username]
        if obj_ui:
            node_obj.update(obj_ui)
            users[username] = node_obj
        else:
            del users[username]
    return users


def get_generic_user_rules(node, policy):
    rules = {}
    rules['%s.users' % policy['path']] = users_list
    return rules


# End user policies

RULES_NODE = {
    'computer': {
        'save': {},
        'policies': {
            'printer_can_view': RULES_PRINTER_CAN_VIEW_RES,
            'repository_can_view': RULES_SOFTWARE_CAN_VIEW_RES,
            'local_users_res': RULES_LOCAL_USERS_RES,
            'package_profile_res': RULES_SOFTWARE_PROFILE_RES,
        },
    },
    'ou': {
        'save': {},
        'policies': {
            'printer_can_view': RULES_PRINTER_CAN_VIEW_RES,
            'repository_can_view': RULES_SOFTWARE_CAN_VIEW_RES,
            'storage_can_view': RULES_STORAGE_CAN_VIEW_RES,
            'local_users_res': RULES_LOCAL_USERS_RES,
            'package_profile_res': RULES_SOFTWARE_PROFILE_RES,
        },
    },
    'group': {
        'save': {},
        'policies': {
            'printer_can_view': RULES_PRINTER_CAN_VIEW_RES,
            'repository_can_view': RULES_SOFTWARE_CAN_VIEW_RES,
            'storage_can_view': RULES_STORAGE_CAN_VIEW_RES,
            'local_users_res': RULES_LOCAL_USERS_RES,
            'package_profile_res': RULES_SOFTWARE_PROFILE_RES,
        },
    },
    'user': {
        'save': {},
        'policies': {
            'storage_can_view': RULES_STORAGE_CAN_VIEW_RES,
        },
    },
    'printer': {
        'save': {
            'printer_can_view': RULES_PRINTER_CAN_VIEW_REVERSE_RES,
        },
        'policies': {},
    },
    'storage': {
        'save': {
            'storage_can_view': RULES_STORAGE_CAN_VIEW_REVERSE_RES,
        },
        'policies': {},
    },
    'repository': {
        'save': {
            'repository_can_view': RULES_SOFTWARE_CAN_VIEW_REVERSE_RES,
        },
        'policies': {},
    },
}


def get_specific_rules(obj_type, rule_type, policy_slug):
    type_rules = RULES_NODE[obj_type][rule_type]
    return type_rules.get(policy_slug, None)


def get_generic_rules(node, policy):
    attrs = node.default.get_dotted(policy['path']).to_dict().keys()
    rules = {}
    for attr in attrs:
        if attr not in EXCLUDE_GENERIC_ATTRS:
            rules['%s.%s' % (policy['path'], attr)] = attr
    return rules


def get_rules(obj_type, rule_type, node, policy):
    rules = get_specific_rules(obj_type, rule_type, policy['slug'])
    if not rules:
        if is_user_policy(policy['path']):
            rules = get_generic_user_rules(node, policy)
        else:
            rules = get_generic_rules(node, policy)
    return rules


def is_user_policy(policy_path):
    from gecoscc.utils import USER_MGMT
    return USER_MGMT in policy_path
