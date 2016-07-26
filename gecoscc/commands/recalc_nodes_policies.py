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
import math
import sys

from optparse import make_option

from bson import ObjectId

from gecoscc.management import BaseCommand
from gecoscc.utils import get_chef_api, recalc_node_policies, get_filter_this_domain


class Command(BaseCommand):
    description = """
        Recalculate the policies of the selected nodes
    """

    option_list = [
        make_option(
            '-c', '--computer',
            dest='computer',
            action='append',
            default=[],
            help='Mongo id of computers'
        ),
        make_option(
            '-d', '--domain',
            dest='domain',
            action='store',
            default=None,
            help='Mongo id of a domain'
        ),
        make_option(
            '-a', '--administrator',
            dest='administrator',
            action='store',
            help='An existing administrator username'
        ),
    ]

    required_options = ('administrator',)

    def get_computers(self):
        '''
        Get the computers from the command arguments.
        '''
        db = self.pyramid.db
        filters = {'type': 'computer'}
        if self.options.domain:
            domain = db.nodes.find_one({'_id': ObjectId(self.options.domain)})
            filters['path'] = get_filter_this_domain(domain)
        elif self.options.computer:
            filters['$or'] = [{'_id': ObjectId(c)} for c in self.options.computer]
        computers = db.nodes.find(filters)
        return computers

    def command(self):
        '''
        This command recalculate the policies of the selected nodes
        These nodes are receiving as command arguments
        '''
        db = self.pyramid.db
        computers = self.get_computers()
        admin_user = db.adminusers.find_one({'username': self.options.administrator})
        if not admin_user:
            sys.stdout.write('Administrator does not exists\n')
            sys.exit(1)
        elif not admin_user.get('is_superuser', None):
            sys.stdout.write('Administrator should be super user\n')
            sys.exit(1)
        api = get_chef_api(self.settings, admin_user)
        cookbook_name = self.settings['chef.cookbook_name']
        num_computers = computers.count()
        # It is not really the max dots, because the integer division.
        max_optimal_dots = 80
        total_dots = min(num_computers, max_optimal_dots)

        if total_dots == num_computers:
            step = 1
        else:
            step = num_computers / total_dots
            total_dots = int(math.ceil(float(num_computers) / step))

        sys.stdout.write('%s 100%%\n' % ('.' * total_dots))
        sys.stdout.flush()
        results_error = {}
        results_succes = {}
        for i, comp in enumerate(computers):
            if i % step == 0:
                sys.stdout.write('.')
                sys.stdout.flush()
            recalculated, reason = recalc_node_policies(db.nodes, db.jobs,
                                                        comp, admin_user,
                                                        cookbook_name, api)
            if recalculated:
                results_succes[comp['name']] = reason
            else:
                results_error[comp['name']] = reason

        sys.stdout.write('\n\n\n*********** Success ********** \n')

        for name, reason in results_succes.items():
            sys.stdout.write('%s: %s \n' % (name, reason))

        sys.stdout.write('\n\n\n*********** Errors ********** \n')

        for name, reason in results_error.items():
            sys.stdout.write('%s: %s \n' % (name, reason))

        sys.stdout.flush()
