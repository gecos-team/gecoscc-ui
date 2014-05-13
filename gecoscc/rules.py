# Network rules

rules_network_res_path = 'gecos_ws_mgmt.network_mgmt.network_res'
rules_network_res_attrs = ('use_dhcp', 'netmask', 'ip_address', 'gateway', 'network_type', 'dns_servers')

RULES_NETWORK_RES = {}

for attr in rules_network_res_attrs:
    RULES_NETWORK_RES['%s.%s' % (rules_network_res_path, attr)] = attr

# end network rules

# Emitter policies

EMITTER_OBJECT_RULES = {
    'printer': ('name', 'manufacturer', 'model', 'uri', 'ppd', 'ppd_uri'),
    'repository': ('name', 'uri', 'components', 'distribution', 'deb_src', 'repo_key', 'key_server'),
    'storage': {'name': 'title',
                'uri': 'uri'}
}


def object_related_list(objs_ui, default=None):
    attrs = EMITTER_OBJECT_RULES.get(objs_ui['type'])
    objs = []
    if isinstance(attrs, tuple):
        for obj_ui in objs_ui['object_related_list']:
            obj = {}
            for attr in attrs:
                obj[attr] = obj_ui[attr]
            objs.append(obj)
    else:
        # if attrs is a dictionary
        raise NotImplementedError
    return objs

# Printer can view
RULES_PRINTER_CAN_VIEW_RES = {'gecos_ws_mgmt.printers_mgmt.printers_res.printers_list': object_related_list}

# Software can view
RULES_SOFTWARE_CAN_VIEW_RES = {'gecos_ws_mgmt.software_mgmt.software_sources_res.repo_list': object_related_list}

# Storage can view
RULES_STORAGE_CAN_VIEW_RES = {'gecos_ws_mgmt.users_mgmt.user_shared_folders_res.users': object_related_list}

# End emitter policies

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
        'save': {},
        'policies': {},
    },
    'storage': {
        'save': {},
        'policies': {},
    },
    'repository': {
        'save': {},
        'policies': {},
    },
}


def get_specific_rules(obj_type, rule_type, policy_slug=None):
    type_rules = RULES_NODE[obj_type][rule_type]
    if rule_type == 'save':
        return type_rules
    if policy_slug in type_rules:
        return type_rules[policy_slug]


def get_generic_rules(node, policy):
    exclude_attrs = ['job_ids', 'jobs_id']
    attrs = node.default.get_dotted(policy['path']).to_dict().keys()
    rules = {}
    for attr in attrs:
        if attr not in exclude_attrs:
            rules['%s.%s' % (policy['path'], attr)] = attr
    return rules


def get_rules(obj_type, rule_type, node, policy=None):
    rules = get_specific_rules(obj_type, rule_type, policy['slug'])
    if not rules:
        rules = get_generic_rules(node, policy)
    return rules
