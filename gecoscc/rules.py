# Network rules

rules_network_res_path = 'gecos_ws_mgmt.network_mgmt.network_res'
rules_network_res_attrs = ('use_dhcp', 'netmask', 'ip_address', 'gateway', 'network_type', 'dns_servers')

RULES_NETWORK_RES = {}

for attr in rules_network_res_attrs:
    RULES_NETWORK_RES['%s.%s' % (rules_network_res_path, attr)] = attr

# end network rules

# Package rules

rules_package_res_path = 'gecos_ws_mgmt.software_mgmt.package_res'
rules_package_res_attrs = ('package_list', 'pkgs_to_remove')

RULES_PACKAGE_RES = {}

for attr in rules_package_res_attrs:
    RULES_PACKAGE_RES['%s.%s' % (rules_package_res_path, attr)] = attr

# End package rules

# Local file rules

rules_local_file_res_path = 'gecos_ws_mgmt.misc_mgmt.local_file_res'
rules_local_file_res_attrs = ('delete_files', 'copy_files')

RULES_LOCAL_FILE_RES = {}

for attr in rules_local_file_res_attrs:
    RULES_LOCAL_FILE_RES['%s.%s' % (rules_local_file_res_path, attr)] = attr
# End local file rules

# Scripts launch rules

rules_scripts_launch_res_path = 'gecos_ws_mgmt.misc_mgmt.scripts_launch_res'
rules_scripts_launch_res_attrs = ('on_startup', 'on_shutdown')

RULES_SCRIPTS_LAUNCH_RES = {}

for attr in rules_scripts_launch_res_attrs:
    RULES_SCRIPTS_LAUNCH_RES['%s.%s' % (rules_scripts_launch_res_path, attr)] = attr
# End Scripts launch rules

# Desktop background res

rules_desktop_background_res_path = 'gecos_ws_mgmt.misc_mgmt.desktop_background_res'
rules_desktop_background_res_attrs = ('desktop_file',)

RULES_DESKTOP_BACKGROUND_RES = {}

for attr in rules_desktop_background_res_attrs:
    RULES_DESKTOP_BACKGROUND_RES['%s.%s' % (rules_desktop_background_res_path, attr)] = attr
# End desktop background res


RULES_NODE = {'computer': {'save': {'gecos_ws_mgmt.network_mgmt.network_res.ip_address': 'ip'},
                           'policies': {'network_res': RULES_NETWORK_RES,
                                        'package_res': RULES_PACKAGE_RES,
                                        'local_file_res': RULES_LOCAL_FILE_RES,
                                        'scripts_launch_res': RULES_SCRIPTS_LAUNCH_RES,
                                        'desktop_background_res': RULES_DESKTOP_BACKGROUND_RES}},
              'ou': {'save': {},
                     'policies': {'network_res': RULES_NETWORK_RES,
                                  'package_res': RULES_PACKAGE_RES,
                                  'local_file_res': RULES_LOCAL_FILE_RES,
                                  'desktop_background_res': RULES_DESKTOP_BACKGROUND_RES}},
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
