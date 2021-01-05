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

from future import standard_library
standard_library.install_aliases()
import json
import requests
import gzip

from bs4 import BeautifulSoup
from optparse import make_option

try:
    from io import StringIO
except ImportError:
    from io import StringIO

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
       Import package data from repositories defined in GECOS CC to MongoDB.

       If the -c option is used, all the data in MongoDB is cleaned before
       importing. Otherwise only new pagkages are imported.
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
        repositories = json.loads(get_setting('repositories', self.settings,
                                              self.db))
        num_packages = 0

        # Fetch repositories packages files
        for repo in repositories:
            print('\n\n\nFetching: ', repo)
            dists_url = repo + 'dists/'
            repo_packages = self.get_packages_urls(dists_url)
            packages_urls[repo] = repo_packages

        print('\n\n\nLooking for new packages...')
        for repo in packages_urls:
            for url in packages_urls[repo]:
                try:
                    r = requests.get(url)
                except requests.exceptions.RequestException:
                    print("Error downloading file: ", url)
                    continue

                packages_list = gzip.GzipFile(fileobj=StringIO(r.content),
                                              mode='rb')
                package_model = Package()
                package = {}
                package['repository'] = repo
                
                try:
                    for line in packages_list:
                        if line.strip() == '':
                            if 'name' in package:
                                packages.append(package['name'])

                                db_package = self.db.packages.find_one(
                                    {'name': package['name']})

                                newVersion = {'version': package['version']}
                                
                                if 'description' in package:
                                    newVersion['description'] = package[
                                        'description']

                                if 'depends' in package:
                                    newVersion['depends'] = package[
                                        'depends']

                                if 'provides' in package:
                                    newVersion['provides'] = package[
                                        'provides']

                                if 'conflicts' in package:
                                    newVersion['conflicts'] = package[
                                        'conflicts']

                                if 'replaces' in package:
                                    newVersion['replaces'] = package[
                                        'replaces']

                                
                                newArchitecture = {'architecture': package[
                                    'architecture'], 'versions': [ newVersion ]}
                                newRepository = {'repository': package[
                                    'repository'], 'architectures': [
                                        newArchitecture ] }                                
                                
                                if not db_package:
                                    # Create new package record
                                    newPackage = {'name': package['name'],
                                                  'repositories': [
                                                      newRepository ]}
                                    
                                    # Check with collander
                                    package_model.serialize(newPackage)

                                    self.db.packages.insert(newPackage)
                                    num_packages += 1
                                    print("Imported package:", package['name'],
                                          " ", package['version'], " ",
                                          package['architecture'])
                                    
                                else:
                                    # Update existing package record
                                    
                                    # Check package repository
                                    current_repo = None
                                    for repodata in db_package['repositories']:
                                        if repodata['repository'] == package[
                                            'repository']:
                                            current_repo = repodata
                                            break
                                    
                                    if current_repo is None:
                                        # Add new repository
                                        db_package['repositories'].append(
                                            newRepository)
                                    
                                    else:
                                        # Check package architecture
                                        current_arch = None
                                        for archdata in current_repo[
                                            'architectures']:
                                            if (archdata['architecture'] ==
                                                package['architecture']):
                                                current_arch = archdata
                                                break

                                        if current_arch is None:
                                            # Add new architecture
                                            current_repo['architectures'
                                                ].append(newArchitecture)
                                            
                                        else:
                                            # Check version
                                            current_ver = None
                                            for verdata in current_arch[
                                                'versions']:
                                                if (verdata['version'] == 
                                                    package['version']):
                                                    current_ver = verdata
                                                    break
                                            
                                            if current_ver is None:
                                                # Add new version
                                                current_arch['versions'
                                                        ].append(newVersion)
                                                
                                    # Update
                                    self.db.packages.update(
                                        {'name':package['name']},
                                        {'$set': db_package})
                                    
                                    print("Updated package:", package['name'],
                                          " ", package['version'], " ",
                                          package['architecture'])

                                
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
                    print("Error decompressing file:", url)
                    continue

        print('\n\nImported %d packages' % num_packages)

        removed = self.db.packages.remove({'name': {'$nin': packages}})
        print('Removed %d packages.\n\n\n' % removed['n'])


    def get_packages_urls(self, url):
        packages = []
        try:
            r = requests.get(url)
        except requests.exceptions.RequestException:
            print("Error parsing repository:", url)
            return packages

        links = self.get_links(r.text)

        if PACKAGES_FILE in links:
            package_url = url + PACKAGES_FILE
            packages.append(package_url)
            print('Found packages file: ', package_url)
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
