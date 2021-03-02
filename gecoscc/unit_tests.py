#
# Copyright 2021, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Abraham Macias <amacias@gruposolutia.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import unittest
from future.backports.datetime import datetime
import json

class TestUtils(unittest.TestCase):

    def test_dict_merge(self):
        from gecoscc.utils import dict_merge
        a = {}
        a['key1'] = 'value1'
        a['key2'] = 'value2'

        a['key4'] = {}
        a['key4']['key1'] = 'value1'
        
        b = {}
        b['key3'] = []
        b['key3'].append('v1')
        b['key3'].append('v2')
        
        b['key4'] = {}
        b['key4']['key2'] = 'value2'
        
        c = {}
        c['key1'] = 'value1'
        c['key2'] = 'value2'

        c['key3'] = []
        c['key3'].append('v1')
        c['key3'].append('v2')
        
        c['key4'] = {}
        c['key4']['key1'] = 'value1'
        c['key4']['key2'] = 'value2'
        
        
        self.assertEqual(dict_merge(a, b), c, "Error in dict merge function!")

        
class TestFilters(unittest.TestCase):

    def test_datetime_filter(self):
        from gecoscc.filters import datetime as datetime_filter
        
        dt = datetime(2007, 4, 1, 15, 30)
        
        self.assertEqual(datetime_filter(dt), '01/04/2007 17:30')
        self.assertEqual(datetime_filter(dt, 'full'),
                         'domingo 1/abr./2007 17:30')


    def test_admin_serialize(self):
        from gecoscc.filters import admin_serialize
        
        admin = { 
            "_id" : "603e091ad3bbc033d81b3a02",
            "is_superuser" : True,
            "username" : "test",
            "email" : "test@example.com",
            "password" : "xxxxx",
        }

        self.assertEqual(json.loads(admin_serialize(admin))['username'],
                         admin['username'])


    def test_timediff(self):
        from gecoscc.filters import timediff

        diff = {
            'timestamp': 1612167143,
            'timestamp_end': 1614676404
        }

        self.assertEqual(timediff(diff), '(29.0d 1.0h 1.0m 1s)')


    def test_regex_match(self):
        from gecoscc.filters import regex_match

        self.assertEqual(regex_match("Hola", "^[a-z]+$", True), True)
        self.assertEqual(regex_match("Hola", "^[a-z]+$", False), False)
        self.assertEqual(regex_match("Hola1", "^[a-z]+$", True), False)



