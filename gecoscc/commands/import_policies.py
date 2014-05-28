import sys

from copy import deepcopy
from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.rules import EXCLUDE_GENERIC_ATTRS
from gecoscc.utils import _get_chef_api, get_cookbook, RESOURCES_EMITTERS_TYPES, emiter_police_slug


DEFAULT_TARGETS = ['ou', 'computer', 'group']
POLICY_EMITTER_TARGETS = {
    'printer_can_view': ['ou', 'computer', 'group'],
    'repository_can_view': ['ou', 'computer', 'group'],
    'storage_can_view': ['user', 'group'],
}

POLICY_EMITTER_NAMES = {
    'printer_can_view': 'Printer can view policy',
    'repository_can_view': 'Repository can view policy',
    'storage_can_view': 'Storage can view policy',
}

POLICY_EMITTER_PATH = {
    'printer_can_view': 'gecos_ws_mgmt.printers_mgmt.printers_res.printers_list',
    'repository_can_view': 'gecos_ws_mgmt.software_mgmt.software_sources_res.repo_list',
    'storage_can_view': 'gecos_ws_mgmt.users_mgmt.user_shared_folders_res.users',
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
            "title": "Object related"
        }
    }
}

EXCLUDE_POLICIES = ('printers_res', 'software_sources_res', 'user_shared_folders_res')


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
            help=('Key of the policy to import. Use multiple times to import multiple policies')
        ),
        make_option(
            '-i', '--ignore-emitter-policies',
            dest='ignore_emitter_policies',
            action='store_true',
            default=False,
            help=('Ignore emitter policies')
        ),
        make_option(
            '-a', '--administrator',
            dest='chef_username',
            action='store',
            help=('An existing chef administrator username')
        ),
        make_option(
            '-k', '--key',
            dest='chef_pem',
            action='store',
            help=('The pem file that contains the chef administrator private key')
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
                            self.options.chef_username,
                            self.options.chef_pem)
        cookbook_name = self.settings['chef.cookbook_name']

        cookbook = get_cookbook(api, cookbook_name)

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
            for ex_attr in EXCLUDE_GENERIC_ATTRS:
                if ex_attr in value['properties']:
                    del(value['properties'][ex_attr])
            path = value.pop('path')
            if 'users_mgmt' in path:
                targets = ['user']
                title = value['title']
                value = value['properties']['users']['items']
                if 'required' in value and 'username' in value['required']:
                    value['required'].pop(value['required'].index('username'))
                if 'username' in value['properties'] and 'username' in value['properties']:
                    value['properties'].pop('username')
                value['title'] = title
            elif 'network_mgmt' in path:
                targets = ['computer']
            else:
                targets = DEFAULT_TARGETS
            policy = {
                'name': value['title'],
                'slug': key,
                'path': path,
                'schema': value,
                'targets': targets,
                'is_emitter_policy': False
            }
            self.treatment_policy(policy)
        if not self.options.ignore_emitter_policies:
            for emiter in RESOURCES_EMITTERS_TYPES:
                schema = deepcopy(SCHEMA_EMITTER)
                schema['properties']['object_related_list']['title'] = '%s list' % emiter.capitalize()
                slug = emiter_police_slug(emiter)
                policy = {
                    'name': POLICY_EMITTER_NAMES[slug],
                    'slug': slug,
                    'path': POLICY_EMITTER_PATH[slug],
                    'targets': POLICY_EMITTER_TARGETS[slug],
                    'is_emitter_policy': True,
                    'schema': schema,
                }
                self.treatment_policy(policy)