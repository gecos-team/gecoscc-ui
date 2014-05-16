from copy import deepcopy

# Network rules

rules_network_res_path = 'gecos_ws_mgmt.network_mgmt.network_res'
rules_network_res_attrs = ('use_dhcp', 'netmask', 'ip_address', 'gateway', 'network_type', 'dns_servers')

RULES_NETWORK_RES = {}

for attr in rules_network_res_attrs:
    RULES_NETWORK_RES['%s.%s' % (rules_network_res_path, attr)] = attr

# end network rules

# Emitter policies

EMITTER_OBJECT_RULES = {
    'printer': ('name', 'manufacturer', 'model', 'uri', 'ppd_uri'),
    'repository': {'repo_name': 'name',
                   'uri': 'uri',
                   'components': 'components',
                   'distribution': 'distribution',
                   'deb_src': 'deb_src',
                   'repo_key': 'repo_key',
                   'key_server': 'key_server'},
    'storage': {'title': 'name',
                'uri': 'uri'}
}


def object_related_list(objs_ui, **kwargs):
    attrs = EMITTER_OBJECT_RULES.get(objs_ui['type'])
    objs = []
    for obj_ui in objs_ui['object_related_list']:
        obj = {}
        if isinstance(attrs, tuple):
            for attr in attrs:
                obj[attr] = obj_ui[attr]
        elif isinstance(attrs, dict):
            for obj_attr, obj_ui_attr in attrs.items():
                obj[obj_attr] = obj_ui[obj_ui_attr]
        objs.append(obj)
    return objs


def object_related_list_reverse(obj_emiter, obj_receptor, node, field_chef, **kwargs):
    raise NotImplementedError


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
RULES_STORAGE_CAN_VIEW_REVERSE_RES = {'gecos_ws_mgmt.users_mgmt.user_shared_folders_res.users': storage_related}

# End emitter policies

# User policies


def users_list(obj_ui, obj, node, field_chef, *kwargs):
    users = deepcopy(node.attributes.get_dotted(field_chef))
    obj_ui['username'] = obj['name']
    update = False
    for i, user in enumerate(users):
        if user['username'] == obj['name']:
            users[i] = obj_ui
            update = True
            break
    if not update:
        users.append(obj_ui)
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
            'network_res': RULES_NETWORK_RES,
            'printer_can_view': RULES_PRINTER_CAN_VIEW_RES,
            'repository_can_view': RULES_SOFTWARE_CAN_VIEW_RES,
        },
    },
    'ou': {
        'save': {},
        'policies': {
            'printer_can_view': RULES_PRINTER_CAN_VIEW_RES,
            'repository_can_view': RULES_SOFTWARE_CAN_VIEW_RES,
        },
    },
    'group': {
        'save': {},
        'policies': {
            'printer_can_view': RULES_PRINTER_CAN_VIEW_RES,
            'repository_can_view': RULES_SOFTWARE_CAN_VIEW_RES,
            'storage_can_view': RULES_STORAGE_CAN_VIEW_RES,
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
            'repository_can_view': RULES_SOFTWARE_CAN_VIEW_REVERSE_RES,
        },
        'policies': {},
    },
    'storage': {
        'save': {
            'printer_can_view': RULES_PRINTER_CAN_VIEW_REVERSE_RES,
            'repository_can_view': RULES_SOFTWARE_CAN_VIEW_REVERSE_RES,
        },
        'policies': {},
    },
    'repository': {
        'save': {
            'printer_can_view': RULES_PRINTER_CAN_VIEW_REVERSE_RES,
            'repository_can_view': RULES_SOFTWARE_CAN_VIEW_REVERSE_RES,
        },
        'policies': {},
    },
}


def get_specific_rules(obj_type, rule_type, policy_slug):
    type_rules = RULES_NODE[obj_type][rule_type]
    return type_rules[policy_slug]


def get_generic_rules(node, policy):
    exclude_attrs = ['job_ids']
    attrs = node.default.get_dotted(policy['path']).to_dict().keys()
    rules = {}
    for attr in attrs:
        if attr not in exclude_attrs:
            rules['%s.%s' % (policy['path'], attr)] = attr
    return rules


def get_rules(obj_type, rule_type, node, policy):
    rules = get_specific_rules(obj_type, rule_type, policy['slug'])
    if not rules:
        if obj_type == 'user':
            rules = get_generic_user_rules(node, policy)
        else:
            rules = get_generic_rules(node, policy)
    return rules
