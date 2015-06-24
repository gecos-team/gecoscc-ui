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

from gecoscc.management import BaseCommand
from gecoscc.models import SoftwareProfile
from gecoscc.command_util import get_setting


class Command(BaseCommand):
    def command(self):
        profiles = json.loads(get_setting('software_profiles', self.settings, self.db))
        collection = self.db.software_profiles

        profile_model = SoftwareProfile()

        for new_profile in profiles:
            name = new_profile['name']
            db_profile = collection.find_one({'name': name})

            if not db_profile:
                collection.insert(new_profile)
                print "Imported profile: %s" % name

            elif new_profile['packages'] != db_profile['packages']:
                collection.update({'name': name}, new_profile)
                print "Updated profile: %s" % name

