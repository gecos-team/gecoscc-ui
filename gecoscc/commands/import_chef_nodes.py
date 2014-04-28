import sys

from optparse import make_option

from chef import Node as ChefNode

from gecoscc.management import BaseCommand
from gecoscc.utils import _get_chef_api, register_node


DEFAULT_TARGETS = ['ou', 'computer']


class Command(BaseCommand):
    description = """
       Import existing nodes in chef server.

    """

    usage = "usage: %prog config_uri create_chef_nodes --administrator user --key file.pem"

    option_list = [
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

    def create_root_ou(self, ou_name):
        data = {'name': ou_name,
                'type': 'ou'}
        ou = self.db.nodes.find_one(data)
        if ou:
            print "OU with name 'ou_0' already exists in mongo"
        else:
            data.update({'extra': '',
                         'path': 'root',
                         'lock': False,
                         'policies': {},
                         'source': 'gecos'})
            ou_id = self.db.nodes.insert(data)
            print "OU with name 'ou_0' created in mongo"
            ou = self.db.nodes.find_one({'_id': ou_id})
        return ou

    def command(self):
        api = _get_chef_api(self.settings.get('chef.url'),
                            self.options.chef_username,
                            self.options.chef_pem)
        ou_name = 'ou_0'
        ou = self.create_root_ou(ou_name)
        for node_id in ChefNode.list():
            node_mongo_id = register_node(api, node_id, ou, self.db.nodes)
            if not node_mongo_id:
                print "%s does not exists" % node_id
