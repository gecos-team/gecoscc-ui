import json
import requests
import gzip
import os
import tempfile
import tarfile

try:
   from cStringIO import StringIO
except ImportError:
   from StringIO import StringIO

from gecoscc.management import BaseCommand
from gecoscc.models import PrinterModel

PPD = 'PPD'

class Command(BaseCommand):
    def command(self):
        urls = json.loads(self.settings.get('printers.urls'))

        collection = self.db.printers
        printer_model = PrinterModel()

        manufacturers = set()
        models = []

        for url in urls:
            try:
                res = requests.get(url)
            except requests.exceptions.RequestException:
                print 'Error downloading file:', url

            temp = tempfile.NamedTemporaryFile(suffix='.tar.gz')
            temp.write(StringIO(res.content).read())
            temp.flush()

            tar = tarfile.open(temp.name)
            members = tar.getmembers()

            for member in members:
                path = member.name.split('/')
                try:
                    ppd_index = path.index(PPD)
                    manufacturer = path[ppd_index + 1]
                    manufacturers.add(manufacturer)
                except (ValueError, IndexError) as err:
                    continue

                filename = path[-1]
                ext = filename.split('.')[-1]
                if ext == 'ppd':
                    ppd_file = tar.extractfile(member)
                    model = self.parse_model(ppd_file)
                    models.append(model)

                    new_printer = printer_model.serialize({'manufacturer': manufacturer, 'model': model})
                    db_printer = collection.find_one({'model': model})

                    if not db_printer:
                        collection.insert(new_printer)
                        print "Imported printer: %s" % model

            temp.close()

        removed = collection.remove({'model': {'$nin': models}})
        print '\n\n\nRemoved %d printers.' % removed['n']


    def parse_model(self, ppd):
        for line in ppd:
            try:
                key_value = line.split(':')
                if key_value[0][1:] == 'ModelName':
                    return key_value[1].strip()[1:-1]
            except IndexError:
                continue
