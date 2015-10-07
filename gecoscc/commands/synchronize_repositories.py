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

try:
   from cStringIO import StringIO
except ImportError:
   from StringIO import StringIO

from gecoscc.management import BaseCommand
from gecoscc.models import Package
from gecoscc.command_util import get_setting

PACKAGES_FILE = 'Packages.gz'
PACKAGE_NAME_TOKEN = 'Package'

class Command(BaseCommand):
    def command(self):
        packages = []
        packages_urls = []
        repositories = json.loads(get_setting('repositories', self.settings, self.db))
        num_packages = 0

        for repo in repositories:
            print '\n\n\nFetching: ', repo
            dists_url = repo + 'dists/'
            repo_packages = self.get_packages_urls(dists_url)
            packages_urls.extend(repo_packages)

        print '\n\n\nLooking for new packages...'
        for url in packages_urls:
            try:
                r = requests.get(url)
            except requests.exceptions.RequestException:
                print "Error downloading file: ", url
                continue

            packages_list = gzip.GzipFile(fileobj=StringIO(r.content), mode='rb')
            package_model = Package()
            package = {}

            try:
                for line in packages_list:
                    try:
                        key_value = self.parse_line(line)
                    except IndexError:
                        continue

                    if key_value['key'] == PACKAGE_NAME_TOKEN:
                        package['name'] = key_value['value']
                        packages.append(package['name'])

                        new_package = package_model.serialize(package)
                        db_package = self.db.packages.find_one({'name': package['name']})

                        if not db_package:
                            self.db.packages.insert(new_package)
                            num_packages += 1
                            print "Imported package:", package['name']
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
