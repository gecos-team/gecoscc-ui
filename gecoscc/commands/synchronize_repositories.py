#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Alberto Beiztegui <albertobeiz@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import json
import requests
import gzip
import threading

from BeautifulSoup import BeautifulSoup
from optparse import make_option

try:
   from cStringIO import StringIO
except ImportError:
   from StringIO import StringIO

from gecoscc.management import BaseCommand
from gecoscc.models import Package
from gecoscc.command_util import get_setting

PACKAGES_FILE = 'Packages.gz'
PACKAGE_NAME_TOKEN = 'Package'
VERSION_TOKEN = 'Version'
ARCHITECTURE_TOKEN = 'Architecture'
DESCRIPTION_TOKEN = 'Description'
DEPENDS_TOKEN = 'Depends'
PROVIDES_TOKEN = 'Provides'
CONFLICTS_TOKEN = 'Conflicts'
REPLACES_TOKEN = 'Replaces'



class Command(BaseCommand):
    description = """
       Import package data from repositories defined in gecosc.ini to MongoDB.

       If the -c option is used, all the data in MongoDB is cleaned before importing. Otherwise only new pagkages are imported.
    """

    usage = "usage: %prog config_uri synchronize_repositories [-c]"

    option_list = [
        make_option(
            '-c', '--clean',
            dest='clean',
            action='store_true',
            default=False,
            help='Clean all data in MongoDB before importing'
        ),
    ]

    required_options = (
    )


    def command(self):
        # Clean the database if necessary
        if self.options.clean:
            print('Cleaning MongoDB data before importing...')
            self.db.packages.drop()
            
        else:
            print('Adding package information to existing data...')
            
    
        packages = []
        packages_urls = {}
        repositories = json.loads(get_setting('repositories', self.settings, self.db))
        num_packages = 0

        # Fetch repositories packages files
        for repo in repositories:
            print '\n\n\nFetching: ', repo
            dists_url = repo + 'dists/'
            repo_packages = self.get_packages_urls(dists_url)
            packages_urls[repo] = repo_packages

        print '\n\n\nLooking for new packages...'
        for repo in packages_urls:
            for url in packages_urls[repo]:
                try:
                    r = requests.get(url)
                except requests.exceptions.RequestException:
                    print "Error downloading file: ", url
                    continue

                packages_list = gzip.GzipFile(fileobj=StringIO(r.content), mode='rb')
                package_model = Package()
                package = {}
                package['repository'] = repo
                
                try:
                    for line in packages_list:
                        if line.strip() == '':
                            if 'name' in package:
                                packages.append(package['name'])

                                new_package = package_model.serialize(package)
                                db_package = self.db.packages.find_one(
                                    {
                                     'name': package['name'], 
                                     'version': package['version'], 
                                     'architecture': package['architecture'],
                                     'repository': package['repository']
                                    })

                                if not db_package:
                                    self.db.packages.insert(package)
                                    num_packages += 1
                                    print "Imported package:", package['name'], " ", package['version'], " ", package['architecture']
                                
                            package = {}
                            package['repository'] = repo
                                
                                
                        else:
                            try:
                                key_value = self.parse_line(line)
                            except IndexError:
                                continue

                            if key_value['key'] == PACKAGE_NAME_TOKEN:
                                package['name'] = key_value['value']
                                
                            if key_value['key'] == VERSION_TOKEN:
                                package['version'] = key_value['value']

                            if key_value['key'] == ARCHITECTURE_TOKEN:
                                package['architecture'] = key_value['value']

                            if key_value['key'] == DESCRIPTION_TOKEN:
                                package['description'] = key_value['value']

                            if key_value['key'] == DEPENDS_TOKEN:
                                package['depends'] = key_value['value']

                            if key_value['key'] == PROVIDES_TOKEN:
                                package['provides'] = key_value['value']

                            if key_value['key'] == CONFLICTS_TOKEN:
                                package['conflicts'] = key_value['value']

                            if key_value['key'] == REPLACES_TOKEN:
                                package['replaces'] = key_value['value']
                            
                            
                except IOError:
                    print "Error decompressing file:", url
                    continue

        print '\n\nImported %d packages' % num_packages

        removed = self.db.packages.remove({'name': {'$nin': packages}})
        print 'Removed %d packages.\n\n\n' % removed['n']


    def get_packages_urls(self, url):
        packages = []
        try:
            r = requests.get(url)
        except requests.exceptions.RequestException:
            print "Error parsing repository:", url
            return packages

        links = self.get_links(r.text)

        if PACKAGES_FILE in links:
            package_url = url + PACKAGES_FILE
            packages.append(package_url)
            print 'Found packages file: ', package_url
        else:
            for link in links:
                if link[-1] == '/':
                    packages.extend(self.get_packages_urls(url + link))

        return packages


    def get_links(self, html):
        links = []
        soup = BeautifulSoup(html)

        for link in soup.findAll("a"):
            href = link.get("href")
            if href[0] not in ['?','/']:
                links.append(link.get("href"))

        return links


    def parse_line(self, line):
        key_value = line.split(':')
        return {'key': key_value[0], 'value': key_value[1].strip()}
