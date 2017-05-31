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
import tempfile
import tarfile
import re

import xml.etree.ElementTree as ET

try:
    from cStringIO import StringIO
except ImportError:
    from StringIO import StringIO

from gecoscc.management import BaseCommand
from gecoscc.models import PrinterModel
from gecoscc.command_util import get_setting

PPD = 'PPD'
PRINTER = 'printer'
DRIVER = 'driver'
postscript_re = re.compile(u'Postscript', re.IGNORECASE)


class Command(BaseCommand):
    def command(self):
        urls = json.loads(get_setting('printers.urls', self.settings, self.db))

        collection = self.db.printer_models
        printer_model = PrinterModel()

        models = []
        num_imported = 0

        print '\n\nDownloading printers lists...'

        for url in urls:
            try:
                res = requests.get(url)
            except requests.exceptions.RequestException:
                print 'Error downloading file:', url
                continue

            temp = tempfile.NamedTemporaryFile(suffix='.tar.gz')
            temp.write(StringIO(res.content).read())
            temp.flush()

            tar = tarfile.open(temp.name)
            members = tar.getmembers()
            for member in members:
                path = member.name.split('/')
                model = ''

                try:
                    file_name = path[-1]
                    ext = file_name.split('.')[-1]
                except IndexError:
                    continue

                if ext == 'xml' and (path[-2] == PRINTER or path[-2] == DRIVER):
                    xml_file = tar.extractfile(member)
                    manufacturer, model = self.parse_model_xml(xml_file.read())

                if model:
                    models.append(model)
                    new_printer = printer_model.serialize({'manufacturer': manufacturer, 'model': model})
                    db_printer = collection.find_one({'model': model})

                    if not db_printer:
                        collection.insert(new_printer)
                        num_imported += 1
                        print "Imported printer: %s" % model

            temp.close()

        print '\n\nImported %d printers' % num_imported

        removed = collection.remove({'model': {'$nin': models}})
        print 'Removed %d printers.\n\n' % removed['n']

    def parse_model_xml(self, xml):
        manufacturer = ''
        model = ''
        root = ET.fromstring(xml)
        for m in root.findall('make'):
            manufacturer = m.text.capitalize()

        for m in root.findall('model'):
            model = m.text
        return manufacturer, model
