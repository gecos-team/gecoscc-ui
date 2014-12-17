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

class Command(BaseCommand):
    def command(self):
        profiles = json.loads(self.settings.get('software_profiles'))
        collection = self.db.software_profiles

        profile_model = SoftwareProfile()

        for name in profiles:
            new_profile = profile_model.serialize({'name': name, 'packages': profiles[name]})
            db_profile = collection.find_one({'name': name})

            del new_profile['_id']

            if not db_profile:
                collection.insert(new_profile)
                print "Imported profile: %s" % name

            elif new_profile['packages'] != db_profile['packages']:
                collection.update({'name': name}, new_profile)
                print "Updated profile: %s" % name

