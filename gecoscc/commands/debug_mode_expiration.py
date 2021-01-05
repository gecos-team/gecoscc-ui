#
# Copyright 2018, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Abraham Macias <amacias@solutia-it.es>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from builtins import str
import sys
from copy import deepcopy
import datetime
import dateutil.parser as dt

from optparse import make_option

from gecoscc.management import BaseCommand
from gecoscc.tasks import object_changed

import logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)    
logger.setLevel(logging.INFO)
    
class Command(BaseCommand):
    description = """
       Check if the debug mode policy set in a computer has expired.
       For all expired policies the debug mode is disabled.
    """

    usage = "usage: %prog config_uri debug_mode_expiration --administrator user"

    option_list = [
        make_option(
            '-a', '--administrator',
            dest='admin_username',
            action='store',
            help='An existing super administrator username'
        ),
    ]

    required_options = (
        'admin_username',
    )
    
    
    
    def command(self):
        # Initialization
        self.db = self.pyramid.db
        
        logger.info('Check administrator username...')
        user = self.db.adminusers.find_one({"username": self.options.admin_username})
        if user is None:
            logger.error('Can\'t find administrator user: %s'%(self.options.admin_username))
            sys.exit(-1)
            
        
        logger.info('Get debug mode policy ID...')
        policy = self.db.policies.find_one({"slug": "debug_mode_res"})
        if policy is None:
            logger.error('Can\'t find debug_mode_res policy')
            sys.exit(-1)
                
        
        logger.info('Checking computer nodes that has this policy applied...')
        field = 'policies.' + str(policy['_id']) + '.enable_debug'
        
        logger.debug('db.nodes.find({"type": "computer", "%s": true}, {"logs":0, "inheritance":0}).pretty()'%(field))
        nodes = self.db.nodes.find({'type': 'computer', field: True}, {"logs":0, "inheritance":0})    
        for node in nodes:
            # Check expire date field existance
            if not 'expire_datetime' in node['policies'][str(policy['_id'])]:
                logger.error('Node %s contains a debug mode policy without expire_datetime!'%(node['_id']))
                continue

            expire_datetime = dt.parse(
                node['policies'][str(policy['_id'])]['expire_datetime'])
            now = datetime.datetime.now(expire_datetime.tzinfo)
            logger.debug('Node %s, expire_datetime: %s now: %s'%(node['_id'], expire_datetime, now))
            if expire_datetime < now:
                logger.info('Node %s debug mode policy expired'%(node['_id']))
                computer = deepcopy(node)
                
                # Set enable_debug to false
                computer['policies'][str(policy['_id'])]['enable_debug'] = False
                self.db.nodes.update_one({'_id': computer['_id']}, {'$set': {field: False} })
                object_changed(user, 'computer', computer, node, computers=[computer])

                
            
        
        logger.info('END ;)')
        