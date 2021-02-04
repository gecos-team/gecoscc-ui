#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Jose Manuel Rodriguez Caro <jmrodriguez@gruposolutia.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import requests
import sys

import xml.etree.ElementTree as ET
from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.utils import _get_chef_api, get_cookbook, toChefUsername
from gecoscc.models import ServiceProvider


class Command(BaseCommand):
    description = """
       Import Mobile BroadBand service providers.
    """

    usage = "usage: %prog config_uri mobile_broadband_providers --administrator user --key file.pem"

    option_list = [
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

        collection = self.db.serviceproviders
        sp_model = ServiceProvider()

        chef_ssl_verify = True if self.settings.get('chef.ssl.verify') == "True" else False

        api = _get_chef_api(self.settings.get('chef.url'),
                            toChefUsername(self.options.chef_username),
                            self.options.chef_pem, chef_ssl_verify, self.settings.get('chef.version'))
        cookbook_name = self.settings['chef.cookbook_name']

        cookbook = get_cookbook(api, cookbook_name)

        for f in cookbook['files']:
            if f['name'] == 'serviceproviders.xml': 
                try:
                    xml = requests.get(f['url'], verify=chef_ssl_verify)
                    break
                except requests.exceptions.RequestException as e:
                    print(e)
                    sys.exit(1)

        # Parsing XML
        root = ET.fromstring(xml.text)
        for country in root.findall('country'):

            for providername in country.findall('provider/name'):

                if providername.text:
                    try:
                        new_sp=sp_model.serialize({'name': country.get('code').lower(), 'provider': providername.text})
                        print(new_sp)
                        collection.insert_one(new_sp)
                    except:
                        print("ERROR:" + providername.text)
                  

