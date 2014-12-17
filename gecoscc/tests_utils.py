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

import json
import time

import requests

from optparse import make_option

from bson import ObjectId

from chef import Node as ChefNode

from gecoscc.management import BaseCommand
from gecoscc.models import OrganisationalUnit
from gecoscc.rules import is_user_policy
from gecoscc.utils import get_chef_api


def waiting_to_celery(db):
    print 'waiting to celery'
    current_jobs_count = db.jobs.count()
    print 'Current jobs: %s' % current_jobs_count
    time.sleep(10)
    current_jobs_count2 = db.jobs.count()
    if current_jobs_count2 > current_jobs_count:
        waiting_to_celery(db)


class PolicyAddCommand(BaseCommand):

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
        ou, admin, policy = self.check_input()
        if not ou:
            return
        ou['policies'][unicode(policy['_id'])] = self.policy_data
        if not self.save_ou(ou, admin):
            return
        waiting_to_celery(db)
        if is_user_policy(policy['path']):
            computer_errors = self.check_users(ou, admin, policy)
        else:
            computer_errors = self.check_computers(ou, admin, policy)
        self.print_error(computer_errors)

    def check_input(self):
        db = self.pyramid.db
        ou = db.nodes.find_one({'_id': ObjectId(self.options.ou_id)})
        if not ou:
            print 'Error OU does not exists'
            return (None, None, None)
        admin = db.adminusers.find_one({'username': self.options.gcc_username})
        if not admin:
            print 'Error this admin does not exists'
            return (None, None, None)
        elif not admin.get('is_superuser', None):
            print 'You need a super admin'
            return (None, None, None)
        policy = db.policies.find_one({"slug": self.policy_slug})
        if not policy:
            print 'Does not exists the package policy'
            return (None, None, None)
        policy_instance = ou['policies'].get(unicode(policy['_id']), None)
        if policy_instance:
            print 'Please remove package policy from the ou: %s' % self.options.ou_id
            return (None, None, None)
        return (ou, admin, policy)

    def save_ou(self, ou, admin):
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
            return True
        else:
            print 'Unknow error saving ou'
            return False

    def check_users(self, ou, admin, policy):
        db = self.pyramid.db
        ou_path = '%s,%s' % (ou['path'], unicode(ou['_id']))
        users = db.nodes.find({'path': ou_path,
                               'type': 'user'})
        computers_error = {}
        api = get_chef_api(self.settings,
                           admin)
        for user in users:
            computers_ids = user.get('computers', [])
            computers = db.nodes.find({'_id': {'$in': computers_ids}})
            policy_attr_to_check = self.get_policy_attr_to_check(policy, user)
            for computer in computers:
                node_id = computer.get('node_chef_id', None)
                if not node_id:
                    computers_error[computer['name']] = 'does not node_chef_id'
                node = ChefNode(node_id, api)
                if self.check_node(policy_attr_to_check, node):
                    print '%s ok' % computer['name']
                else:
                    computers_error[computer['name']] = self.error % user['name']
        return computers_error

    def check_computers(self, ou, admin, policy):
        db = self.pyramid.db
        ou_path = '%s,%s' % (ou['path'], unicode(ou['_id']))
        computers = db.nodes.find({'path': ou_path,
                                   'type': 'computer'})
        api = get_chef_api(self.settings,
                           admin)
        computers_error = {}
        policy_attr_to_check = self.get_policy_attr_to_check(policy)
        for computer in computers:
            node_id = computer.get('node_chef_id', None)
            if not node_id:
                computers_error[computer['name']] = 'does not node_chef_id'
            node = ChefNode(node_id, api)
            if self.check_node(policy_attr_to_check, node):
                print '%s ok' % computer['name']
            else:
                computers_error[computer['name']] = self.error
        return computers_error

    def print_error(self, computers_error):
        if not computers_error:
            print 'Test succesfully'
        else:
            print 'The test is not completed succesfully'
            for computer_name, computer_error in computers_error.items():
                print 'Error at %s: %s' % (computer_name, computer_error)
