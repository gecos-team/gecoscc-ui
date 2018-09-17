#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Antonio Perez-Aranda <ant30tx@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from cornice.resource import resource

import pyramid.threadlocal
from pyramid.threadlocal import get_current_registry

from gecoscc.api import ResourcePaginatedReadOnly
from gecoscc.models import Update, Updates
from gecoscc.permissions import api_login_required
from gecoscc.socks import socktail
from pyramid.httpexceptions import HTTPBadRequest

import os
import re
import threading
import subprocess
import pymongo
import logging
logger = logging.getLogger(__name__)

COLORS = {
    'INFO':'green', 
    'DEBUG':'blue',
    'WARNING':'orange',
    'ERROR':'red',
    'default': 'black'
}


@resource(collection_path='/api/updates/',
          path='/api/updates/{oid}/',
          description='Updates resource',
          validators=(api_login_required,))
class UpdateResource(ResourcePaginatedReadOnly):

    schema_collection = Updates
    schema_detail = Update
    objtype = 'updates'
    order_field = [('_id', pymongo.DESCENDING)]

    mongo_filter = {}

    collection_name = objtype

    def get_oid_filter(self, oid):
        return {self.key: oid}

    def tail_f(self, file):
        while True:
            where = file.tell()
            line = file.readline()
            if not line:
                file.seek(where)
                lsof = subprocess.check_output(['lsof', file.name])
                if len(lsof.split("\n")) <= 3:
                    break
            else:
                yield line

    def simple_logparser(self, line):
        regex = '(.*(INFO|ERROR|DEBUG|WARNING).*)'
        match = re.match(regex, line)
        if (match is None):
            matched = 'default'
        else:
            matched = match.group(2)
            logger.debug('tail.py ::: simple_logparser - match.group(2) = %s' % match.group(2))

        logger.debug('tail.py ::: simple_logparser - matched = %s' % matched)
        logger.debug('tail.py ::: simple_logparser - COLORS[matched] = %s' % COLORS[matched])
         
        line = '<p style="color:{0}">{1}</p>'.format(COLORS[matched],line)
 
        return line

    def reader(self, filename, pyramid_thread_locals):
        pyramid.threadlocal.manager.push(pyramid_thread_locals)
        for line in self.tail_f(open(filename)):
            socktail(self.simple_logparser(line))

    def get(self):

        oid = self.request.matchdict['oid']
        tail = self.request.GET.get('tail', None)
        rollback = self.request.GET.get('rollback', '')
        logger.debug('TAILRESOURCE: tail = %s' % tail)
        logger.debug('TAILRESOURCE: rollback = %s' % rollback)
     
        if tail:
            settings = get_current_registry().settings

            logfile = settings['updates.rollback'].format(oid) if rollback else settings['updates.log'].format(oid)
            logger.debug('TAILRESOURCE: logfile = %s' % logfile)

            if os.path.exists(logfile):
                pyramid_thread_locals = pyramid.threadlocal.manager.get()
                t = threading.Thread(target=self.reader, args=(logfile, pyramid_thread_locals, ))
                t.start()
            else:
                raise HTTPBadRequest()
            
            logger.debug('TAILRESOURCE: ENDING')
            return 

        return super(UpdateResource, self).get()
