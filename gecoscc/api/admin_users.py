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

import os

from cornice.resource import resource

from pyramid.threadlocal import get_current_registry
from gecoscc.command_util import get_setting

from gecoscc.api import BaseAPI
from gecoscc.models import AdminUserVariables
from gecoscc.permissions import http_basic_login_required
from gecoscc.utils import get_pem_for_username


@resource(path='/auth/config/',
          description='Auth config',
          validators=http_basic_login_required)
class AdminUserResource(BaseAPI):

    schema_detail = AdminUserVariables
    collection_name = 'adminusers'

    def get(self):
        user = self.request.user
        variables = self.parse_item(user.get('variables', {}))
        settings = get_current_registry().settings

        chef = {}
        chef['chef_server_uri'] = settings.get('chef.url')
        chef['chef_link'] = True
        chef['chef_validation'] = get_pem_for_username(settings, user['username'], 'chef_client.pem')

        gcc = {}
        gcc['gcc_link'] = True
        gcc['uri_gcc'] = self.request.host_url
        gcc['gcc_username'] = self.request.user['username']

        auth_type = variables.get('auth_type', 'LDAP')
        if auth_type == 'LDAP':
            auth_properties = variables['auth_ldap']
        else:
            if variables['specific_conf'] == 'false':
                auth_properties = {'specific_conf': False,
                                   'ad_properties': variables['auth_ad']}
            else:
                schema = self.schema_detail()
                conf_files = schema.get_config_files('r', user['username'])
                auth_properties = {'specific_conf': True}
                ad_properties = {}
                for conf_file in conf_files:
                    variable_name = conf_file.name.split(os.sep)[-1].replace('.', '_')
                    ad_properties[variable_name] = conf_file.read().encode('base64')
                auth_properties['ad_properties'] = ad_properties
        auth = {'auth_properties': auth_properties,
                'auth_type': auth_type}
        return {'version': get_setting('firstboot_api.version', settings, self.request.db),
                'organization': get_setting('firstboot_api.organization_name', settings, self.request.db),
                'notes': get_setting('firstboot_api.comments', settings, self.request.db),
                'gem_repo': get_setting('firstboot_api.gem_repo', settings, self.request.db),
                'uri_ntp': variables.get('uri_ntp', ''),
                'auth': auth,
                'chef': chef,
                'gcc': gcc}
