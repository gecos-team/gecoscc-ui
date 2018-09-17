#
# Copyright 2017, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Abraham Macias <amacias@solutia-it.es>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

#
# In GECOS CC v2.2 the user must be able to use the search box that is located over
# the nodes tree to look for a computer by using its IPv4 address.
#
# This script is used to update the IPv4 address or every computer node in MongoDB database
# by getting them from the OHAI information of every Chef node.
#

from chef import Node
from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.utils import _get_chef_api, toChefUsername

class Command(BaseCommand):
    description = """
       Get the IPv4 address or every Chef node and update the "ipaddress" field of the MongoDB node.
    """

    usage = "usage: %prog config_uri update_ip_address --administrator user --key file.pem"

    option_list = [
        make_option(
            '-a', '--administrator',
            dest='chef_username',
            action='store',
            help='An existing chef super administrator username (like "pivotal" user)'
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
        api = _get_chef_api(self.settings.get('chef.url'),
                            toChefUsername(self.options.chef_username),
                            self.options.chef_pem, self.settings.get('chef.version'))
                            
        print('INFO: Update IPv4 address START!') 
        db = self.pyramid.db
        computers = db.nodes.find({'type': 'computer'})
        for comp in computers:
            node_id = comp.get('node_chef_id', None)
            node = Node(node_id, api)
            ipaddress = node.attributes.get('ipaddress')
            
            print('INFO: Update node: %s, set IP: %s'%(node_id, ipaddress)) 
            db.nodes.update({'node_chef_id':node_id},{'$set': {'ipaddress':ipaddress}})
        
        print('INFO: Update IPv4 address END!') 
        
