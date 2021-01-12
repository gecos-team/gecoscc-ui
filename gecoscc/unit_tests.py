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

        

