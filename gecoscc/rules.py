rules_network_res_path = 'gecos_ws_mgmt.network_mgmt.network_res'
rules_network_res_attrs = ('use_dhcp', 'netmask', 'ip_address', 'gateway', 'network_type', 'dns_servers')

RULES_NETWORK_RES = {}

for attr in rules_network_res_attrs:
    RULES_NETWORK_RES['%s.%s' % (rules_network_res_path, attr)] = attr


RULES_NODE = {'computer': {'save': {'gecos_ws_mgmt.network_mgmt.network_res.ip_address': 'ip'},
                           'policies': {'network_res': RULES_NETWORK_RES}},
              'ou': {'save': {},
                     'policies': {'network_res': RULES_NETWORK_RES}},
              'group': {'save': {},
                        'policies': {}},
              'user': {'save': {},
                       'policies': {}},
              'printer': {'save': {},
                          'policies': {},
                          'related': {'gecos_ws_mgmt.printer_use.network_res.ip_address': 'ip'}},
              'storage': {'save': {},
                          'policies': {}}
              }
