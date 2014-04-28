import sys

from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.utils import _get_chef_api, get_cookbook


DEFAULT_TARGETS = ['ou', 'computer']
POLICY_NAMES = {
    'local_users_res': 'User policy',
    'local_admin_users_res': 'Administrator policy',
    'desktop_background_res': 'Desktop policy',
    'auto_updates_res': 'Auto update policy',
    'scripts_launch_res': 'Script Launch policy',
    'local_groups_res': 'Group policy',
    'local_file_res': 'Local file policy',
    'tz_date_res': 'Date policy',
}


class Command(BaseCommand):
    description = """
       Import existing policies in chef server.

       If you dont add any -p option then all the policies will be imported.
    """

    usage = "usage: %prog config_uri create_chef_administrator --administrator user --key file.pem -p policy_key1 -p policy_key2"

    option_list = [
        make_option(
            '-p', '--policy',
            dest='policies',
            action='append',
            default=[],
            help=('Key of the policy to import. Use multiple times to import multiple policies')
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

    def command(self):
        api = _get_chef_api(self.settings.get('chef.url'),
                            self.options.chef_username,
                            self.options.chef_pem)
        cookbook_name = self.settings['chef.cookbook_name']

        cookbook = get_cookbook(api, cookbook_name)

        try:
            policies = cookbook['metadata']['attributes']['json_schema']['object']['properties']['gecos_ws_mgmt']['properties']['misc_mgmt']['properties']
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
            if 'jobs_id' in value:
                del(value['jobs_id'])
            policy = {
                'name': POLICY_NAMES.get(key, key),
                'slug': key,
                'schema': value,
                'targets': DEFAULT_TARGETS,
            }
            self.db.policies.insert(policy)
            print "Imported policy: %s" % key
