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
from _io import BytesIO
standard_library.install_aliases()
import json
import requests
import tempfile
import tarfile
import re

import xml.etree.ElementTree as ET

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

        print('\n\nDownloading printers lists...')

        for url in urls:
            try:
                res = requests.get(url)
            except requests.exceptions.RequestException:
                print('Error downloading file:', url)
                continue

            suffix = '.tar.gz'
            if url.endswith('.tar.xz'):
                suffix = '.tar.xz'

            temp = tempfile.NamedTemporaryFile(suffix=suffix)
            temp.write(BytesIO(res.content).read())
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
                    xml_data = xml_file.read().decode('UTF-8')
                    manufacturer, model = self.parse_model_xml(xml_data)

                if model:
                    models.append(model)
                    new_printer = printer_model.serialize(
                        {'manufacturer': manufacturer, 'model': model})
                    db_printer = collection.find_one({'model': model})

                    if not db_printer:
                        collection.insert_one(new_printer)
                        num_imported += 1
                        print("Imported printer: %s" % model)

            temp.close()

        print('\n\nImported %d printers' % num_imported)

        # Adding 'Other' model for every manufacturer
        models.append('Other') # Later, don't remove
        for m in collection.distinct('manufacturer'):
            other = printer_model.serialize(
                {'manufacturer': m, 'model': 'Other'})
            collection.insert_one(other)

        removed = collection.delete_many({'model': {'$nin': models}})
        print('Removed %d printers.\n\n' % removed.deleted_count)

    def parse_model_xml(self, xml):
        manufacturer = ''
        model = ''
        root = ET.fromstring(xml)
        for m in root.findall('make'):
            manufacturer = m.text.capitalize()

        for m in root.findall('model'):
            model = m.text
        return manufacturer, model
