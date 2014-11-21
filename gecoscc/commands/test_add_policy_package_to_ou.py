import json

import requests

from optparse import make_option

from bson import ObjectId

from chef import Node as ChefNode

from gecoscc.management import BaseCommand
from gecoscc.models import OrganisationalUnit
from gecoscc.tests_utils import waiting_to_celery
from gecoscc.utils import get_chef_api


class Command(BaseCommand):
    description = """
        Create nodes
    """
    usage = ("usage: %prog create_nodes"
             "--organisational-unit-id 1234567890abcdef12345678"
             "--gecoscc-url http://localhost --gecoscc-username admin --gecoscc-password admin")

    option_list = [
        make_option(
            '-o', '--organisational-unit-id',
            dest='ou_id',
            action='store',
            help='Organisational unit id'
        ),
        make_option(
            '-s', '--gecoscc-username',
            dest='gcc_username',
            action='store',
            help='An existing gecoscc administrator username'
        ),
        make_option(
            '-p', '--gecoscc-password',
            dest='gcc_password',
            action='store',
            help='The password of the gecoscc administrator'
        ),
        make_option(
            '-u', '--gecoscc-url',
            dest='gcc_url',
            action='store',
            help='The url where gecoscc is running'
        ),
    ]

    required_options = (
        'ou_id',
        'gcc_username',
        'gcc_password',
        'gcc_url',
    )

    def command(self):
        db = self.pyramid.db
        ou = db.nodes.find_one({'_id': ObjectId(self.options.ou_id)})
        if not ou:
            print 'Error OU does not exists'
            return
        admin = db.adminusers.find_one({'username': self.options.gcc_username})
        if not admin:
            print 'Error this admin does not exists'
            return
        elif not admin.get('is_superuser', None):
            print 'You need a super admin'
            return
        package_policy = db.policies.find_one({"slug": "package_res"})
        if not package_policy:
            print 'Does not exists the package policy'
            return
        package_policy_instance = ou['policies'].get(unicode(package_policy['_id']), None)
        if package_policy_instance:
            print 'Please remove package policy from the ou: %s' % self.options.ou_id
            return
        ou['policies'][unicode(package_policy['_id'])] = {"pkgs_to_remove": [], "package_list": ["gimp"]}
        url_api = '%s/api/ous/%s/' % (self.options.gcc_url, self.options.ou_id)
        headers = {'Content-type': 'application/json', 'Accept': 'text/plain'}
        ou_model = OrganisationalUnit()
        ou_json = json.dumps(ou_model.serialize(ou))
        res = requests.put(url_api,
                           ou_json,
                           auth=(self.options.gcc_username,
                                 self.options.gcc_password),
                           headers=headers)
        if res.ok and res.json() == json.loads(ou_json):
            print 'Saving ou sucessfully'
        else:
            print 'Unknow error saving ou'
        waiting_to_celery(db)
        ou_path = '%s,%s' % (ou['path'], unicode(ou['_id']))
        computers = db.nodes.find({'path': ou_path,
                                   'type': 'computer'})
        api = get_chef_api(self.settings,
                           admin)
        computers_error = {}
        policy_attr_to_check = '%s.package_list' % package_policy['path']
        for computer in computers:
            node_id = computer.get('node_chef_id', None)
            if not node_id:
                computers_error[computer['name']] = 'Computer %s does not node_chef_id'
            node = ChefNode(node_id, api)
            if node.attributes.get_dotted(policy_attr_to_check) != ["gimp"]:
                computers_error[computer['name']] = 'Error at %s: the package_list is not ["gimp"]'
            else:
                print '%s ok' % computer['name']
        if not computers_error:
            print 'Test succesfully'
        else:
            print 'The test is not completed succesfully'
            for computer_name, computer_error in computers_error.items():
                print computer_error % computer_name
