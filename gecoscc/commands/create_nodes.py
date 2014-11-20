from optparse import make_option

from bson import ObjectId

from gecoscc.management import BaseCommand


class Command(BaseCommand):
    description = """
        Create nodes
    """
    usage = ("usage: %prog create_nodes --administrator user --key file.pem --number 100000 "
             "--organisational-unit-id 1234567890abcdef12345678 --copy-computer-id 1234567890abcdef12345678")

    option_list = [
        make_option(
            '-n', '--number',
            dest='number',
            action='store',
            help='Number of nodes to create'
        ),
        make_option(
            '-o', '--organisational-unit-id',
            dest='ou_id',
            action='store',
            default=False,
            help='Organisational unit id'
        ),
        make_option(
            '-c', '--copy-computer-id',
            dest='comp_id',
            action='store',
            default=False,
            help='Computer id'
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
    ]

    required_options = (
        'chef_username',
        'chef_pem',
    )

    def command(self):
        db = self.pyramid.db
        ou = db.nodes.find_one({'_id': ObjectId(self.options.ou_id)})
        if not ou:
            print 'Error OU does not exists'
            return
        comp = db.nodes.find_one({'_id': ObjectId(self.options.comp_id)})
        if not comp:
            print 'Error computer does not exists'
            return
        number_nodes = int(self.options.number)
        for i in range(number_nodes):
            print i