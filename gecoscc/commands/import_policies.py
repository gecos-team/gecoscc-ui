#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#   Emilio Sanchez <emilio.sanchez@gmail.com>
#   Alberto Beiztegui <albertobeiz@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import sys

from copy import deepcopy
from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.rules import EXCLUDE_GENERIC_ATTRS, is_user_policy
from gecoscc.utils import _get_chef_api, get_cookbook, RESOURCES_EMITTERS_TYPES, emiter_police_slug, toChefUsername


DEFAULT_TARGETS = ['ou', 'computer', 'group']
POLICY_EMITTER_TARGETS = {
    'printer_can_view': ['ou', 'computer', 'group'],
    'repository_can_view': ['ou', 'computer', 'group'],
    'storage_can_view': ['ou', 'user', 'group'],
}

POLICY_EMITTER_NAMES = {
    'printer_can_view': 'Available printers',
    'repository_can_view': 'Available repositories',
    'storage_can_view': 'Available storages',
}

LANGUAGES = ['es']
POLICY_EMITTER_NAMES_LOCALIZED = {
    'es': {
        'printer_can_view': 'Impresoras disponibles',
        'repository_can_view': 'Repositorios disponibles',
        'storage_can_view': 'Almacenamientos disponibles',
    }
}

EMITTER_LIST_LOCALIZED = {
    'es': 'Lista de %s'
}

EMITTER_LOCALIZED = {
    'es': {
        'printer': 'Impresoras',
        'repository': 'Repositorios',
        'storage': 'Almacenamientos',
    }
}

POLICY_EMITTER_PATH = {
    'printer_can_view': 'gecos_ws_mgmt.printers_mgmt.printers_res.printers_list',
    'repository_can_view': 'gecos_ws_mgmt.software_mgmt.software_sources_res.repo_list',
    'storage_can_view': 'gecos_ws_mgmt.users_mgmt.user_shared_folders_res.users',
}

POLICY_EMITTER_URL = {
    'printer_can_view': '/api/printers/',
    'repository_can_view': '/api/repositories/',
    'storage_can_view': '/api/storages/',
}

SCHEMA_EMITTER = {
    "required": ["object_related_list"],
    "type": "object",
    "properties": {
        "object_related_list": {
            "minItems": 1,
            "uniqueItems": True,
            "items": {
                "enum": [],
                "type": "string",
            },
            "type": "array",
            "autocomplete_url": "",
            "title": "Object related"
        }
    }
}

EXCLUDE_POLICIES = ('printers_res', 'software_sources_res', 'user_shared_folders_res')

PACKAGE_POLICY = 'package_res'
PACKAGE_POLICY_URL = '/api/packages/'

MIMETYPES_POLICY = 'mimetypes_res'
MIMETYPES_POLICY_URL = '/api/mimetypes/'

MOBILE_BROADBAND_POLICY = 'mobile_broadband_res'
MOBILE_BROADBAND_POLICY_URL = '/api/serviceproviders/?country_list=true'

class Command(BaseCommand):
    description = """
       Import existing policies in chef server.

       If you dont add any -p option then all the policies will be imported.
    """

    usage = "usage: %prog config_uri import_policies --administrator user --key file.pem -p policy_key1 -p policy_key2 --ignore-emitter-policies"

    option_list = [
        make_option(
            '-p', '--policy',
            dest='policies',
            action='append',
            default=[],
            help='Key of the policy to import. Use multiple times to import multiple policies'
        ),
        make_option(
            '-i', '--ignore-emitter-policies',
            dest='ignore_emitter_policies',
            action='store_true',
            default=False,
            help='Ignore emitter policies'
        ),
        make_option(
            '-a', '--administrator',
            dest='chef_username',
            action='store',
            help='An existing chef administrator username'
        ),
        make_option(
            '-k', '--key',
            dest='chef_pem',
            action='store',
            help='The pem file that contains the chef administrator private key'
        ),
        make_option(
            '-d', '--delete',
            dest='delete',
            action='store_true',
            default=[],
            help='Delete non imported (probably deprecated) policies'
        ),        
    ]

    required_options = (
        'chef_username',
        'chef_pem',
    )

    def treatment_policy(self, new_policy):
        policy_slug = new_policy['slug']
        db_policy = self.db.policies.find_one({'slug': policy_slug})
        if not db_policy:
            self.db.policies.insert(new_policy)
            print "Imported policy: %s" % policy_slug
        else:
            self.db.policies.update({'slug': policy_slug}, new_policy)
            print "Updated policy: %s" % policy_slug

    def command(self):
        api = _get_chef_api(self.settings.get('chef.url'),
                            toChefUsername(self.options.chef_username),
                            self.options.chef_pem, self.settings.get('chef.ssl.verify'), self.settings.get('chef.version'))
        cookbook_name = self.settings['chef.cookbook_name']

        cookbook = get_cookbook(api, cookbook_name)

        languages = self.settings.get('pyramid.locales')
        languages.remove(self.settings.get('pyramid.default_locale_name'))

        policies = {}
        try:
            for key, value in cookbook['metadata']['attributes']['json_schema']['object']['properties']['gecos_ws_mgmt']['properties'].items():
                for k, policy in value['properties'].items():
                    policy['path'] = '%s.%s.%s' % (cookbook_name, key, k)
                    policies[k] = policy
        except KeyError:
            print "Can not found policies in cookbook %s" % cookbook_name
            sys.exit(1)

        policies_to_import = self.options.policies
        if policies_to_import:
            found = set(policies_to_import).intersection(set(policies.keys()))
            not_found = set(policies_to_import).difference(set(policies.keys()))
            if not_found:
                print "%s policies to import. Policies NOT FOUND: %s" % (len(found), list(not_found))
            else:
                print "%s policies to import" % len(found)
        else:
            print "%s policies to import" % len(policies.keys())

        for key, value in policies.items():
            if policies_to_import and key not in policies_to_import:
                continue
            elif key in EXCLUDE_POLICIES:
                continue
            if key == PACKAGE_POLICY:
                self.set_packages_url(value)
            
            if key == MIMETYPES_POLICY:
                self.set_mimetypes_url(value)

            if key == MOBILE_BROADBAND_POLICY:
                self.set_serviceproviders_url(value)

            support_os = value['properties']['support_os']['default']

            for ex_attr in EXCLUDE_GENERIC_ATTRS:
                if ex_attr in value['properties']:
                    del(value['properties'][ex_attr])

            path = value.pop('path')

            form_layout = value.pop('form', {})
            is_mergeable = value.pop('is_mergeable', False)
            autoreverse = value.pop('autoreverse', False)

            if is_user_policy(path):
                targets = ['ou', 'user', 'group']
                title = value['title']
                titles = {}
                for lan in languages:
                    titles[lan] = value['title_' + lan]

                value = value['properties']['users']['patternProperties']['.*']
                if 'updated_by' in value.get('properties', {}):
                    del value['properties']['updated_by']
                value['title'] = title
                for lan in languages:
                    value['title_' + lan] = titles[lan]

            elif 'single_node' in path:
                targets = ['computer']
            else:
                targets = DEFAULT_TARGETS

            policy = {
                'name': value['title'],
                'slug': key,
                'path': path,
                'schema': value,
                'form': form_layout,
                'targets': targets,
                'is_emitter_policy': False,
                'support_os': support_os,
                'is_mergeable': is_mergeable,
                'autoreverse': autoreverse,
            }

            for lan in languages:
                policy['name_' + lan] = value['title_' + lan]

            self.treatment_policy(policy)

        if not self.options.ignore_emitter_policies:
            for emiter in RESOURCES_EMITTERS_TYPES:
                slug = emiter_police_slug(emiter)
                schema = deepcopy(SCHEMA_EMITTER)
                schema['properties']['object_related_list']['title'] = '%s list' % emiter.capitalize()
                for lan in languages:
                    schema['properties']['object_related_list']['title_' + lan] = EMITTER_LIST_LOCALIZED[lan] % EMITTER_LOCALIZED[lan][emiter]
                schema['properties']['object_related_list']['autocomplete_url'] = POLICY_EMITTER_URL[slug]
                policy = {
                    'name': POLICY_EMITTER_NAMES[slug],
                    'slug': slug,
                    'path': POLICY_EMITTER_PATH[slug],
                    'targets': POLICY_EMITTER_TARGETS[slug],
                    'is_emitter_policy': True,
                    'schema': schema,
                    'support_os': policies[POLICY_EMITTER_PATH[slug].split('.')[2]]['properties']['support_os']['default'],
                    'is_mergeable': True,
                    'autoreverse': policies[POLICY_EMITTER_PATH[slug].split('.')[-2]].get('autoreverse', False)
                }
                for lan in languages:
                    policy['name_' + lan] = POLICY_EMITTER_NAMES_LOCALIZED[lan][slug]
                self.treatment_policy(policy)
                
        # Check non imported policies
        print "Check non imported policies..."
        dbpolicies = self.db.policies.find({})
        found = False
        for policy in dbpolicies:
            if (policy['slug'] not in policies and 
                not policy['slug'].endswith('_can_view')):
                print "Policy '%s' wasn't imported. Probably is deprecated." % (policy['slug'])
                found = True
                if self.options.delete:
                    # Delete deprecated policy
                    self.db.policies.remove({'slug': policy['slug']})
                    print "Policy '%s' deleted!" % (policy['slug'])
                    if policy['slug'] == 'package_profile_res':
                        # Also delete software_profiles collection
                        print "Drop software profiles collection!"
                        self.db.software_profiles.drop()
                        
        if not found:
            print "There are no deprecated policies"
        

    def set_packages_url(self, value):
        value['properties']['package_list']['items']['properties']['name']['autocomplete_url'] = PACKAGE_POLICY_URL
        value['properties']['package_list']['items']['properties']['name']['enum'] = []
        value['properties']['package_list']['items']['properties']['version']['autocomplete_url'] = 'javascript:calculateVersions'
        value['properties']['package_list']['items']['properties']['version']['enum'] = []
    
    def set_mimetypes_url(self, value):
        value['properties']['users']['patternProperties']['.*']['properties']['mimetyperelationship']['items']['properties']['mimetypes']['autocomplete_url'] = MIMETYPES_POLICY_URL
        value['properties']['users']['patternProperties']['.*']['properties']['mimetyperelationship']['items']['properties']['mimetypes']['items']['enum'] = []

    def set_serviceproviders_url(self, value):
        value['properties']['connections']['items']['properties']['country']['autocomplete_url'] = MOBILE_BROADBAND_POLICY_URL
        value['properties']['connections']['items']['properties']['country']['enum'] = []
        value['properties']['connections']['items']['properties']['provider']['autocomplete_url'] = 'javascript:calculateProviders'
        value['properties']['connections']['items']['properties']['provider']['enum'] = []
        