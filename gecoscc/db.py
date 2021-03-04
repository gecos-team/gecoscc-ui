#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Antonio Perez-Aranda <ant30tx@gmail.com>
#   Pablo Martin <goinnn@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

import os
import pymongo
import subprocess
from urllib.parse import urlparse


DEFAULT_MONGODB_HOST = 'localhost'
DEFAULT_MONGODB_PORT = 27017
DEFAULT_MONGODB_NAME = 'gecoscc'
DEFAULT_MONGODB_URI = 'mongodb://%s:%d/%s' % (DEFAULT_MONGODB_HOST,
                                              DEFAULT_MONGODB_PORT,
                                              DEFAULT_MONGODB_NAME)

# Simulates mongodump --excludeCollection option (new in version 3.0)
# Excludes the specified collections from the mongodump output
DEFAULT_EXCLUDE_COLLECTIONS = ['updates','backer_cache']

import logging
logger = logging.getLogger(__name__)

class MongoDB(object):
    """Simple wrapper to get pymongo real objects from the settings uri"""

    def __init__(self, db_uri=DEFAULT_MONGODB_URI,
                 connection_factory=None, **kwargs):

        self.db_uri = db_uri
        self.parsed_uri = pymongo.uri_parser.parse_uri(self.db_uri)

        if 'replicaSet' in kwargs:
            connection_factory = pymongo.MongoReplicaSetClient

        elif connection_factory is None:
            connection_factory = pymongo.MongoClient

        self.connection = connection_factory(
            host=self.db_uri,
            tz_aware=True,
            **kwargs)

        if self.parsed_uri.get("database", None):
            self.database_name = self.parsed_uri["database"]
        else:
            self.database_name = DEFAULT_MONGODB_NAME

    def get_connection(self):
        return self.connection

    def get_database(self, database_name=None):
        if database_name is None:
            db = self.connection[self.database_name]
        else:
            db = self.connection[database_name]
        if self.parsed_uri.get("username", None):
            db.authenticate(
                self.parsed_uri.get("username", None),
                self.parsed_uri.get("password", None)
            )
        self.indexes(db)
        return db

    def indexes(self, db):
        db.nodes.create_index([
            ('node_chef_id', pymongo.DESCENDING),
        ])
        db.nodes.create_index([
            ('path', pymongo.DESCENDING),
            ('type', pymongo.DESCENDING),
        ])
        # TODO: this try/except will be removed in review release
        try:
            db.nodes.create_index([
                ('name', pymongo.DESCENDING),
                ('type', pymongo.DESCENDING),
            ])
        except pymongo.errors.OperationFailure:
            db.nodes.drop_index('name_-1_type_-1')
            db.nodes.create_index([
                ('name', pymongo.DESCENDING),
                ('type', pymongo.DESCENDING),
            ])

        db.jobs.create_index([
            ('userid', pymongo.DESCENDING),
        ])

    def dump(self, path, collection=None, excludes=DEFAULT_EXCLUDE_COLLECTIONS):
        '''
        Back up MongoDB
        Args:
            path (str): backup folder
            collection (str): if this is None, back up database. Otherwise, back up collection
        Returns:
            -
        '''
        logger.info("Starting mongodump ...")
        exitstatus = 0

        if not os.path.exists(path):
            os.mkdir(path)

        command = [
            'mongodump',
            '--host', '%s' % urlparse(self.db_uri).hostname,
            '-d', '%s' % self.database_name,
            '--port', '%s' % urlparse(self.db_uri).port,
            '-o', '%s' % path
        ]


        if self.parsed_uri.get('username', None):
            command += ['-u', '%s' % self.parsed_uri.get('username')]
            command += ['-p', '%s' % self.parsed_uri.get('password')]

        logger.debug("db.py ::: dump - command = %s" % command)

        try:
            if collection:
                command += ['--collection', '%s' % collection]
                dump_output = subprocess.check_output(command)
                logger.debug("db.py ::: dump - dump_output = %s" % dump_output)
            else:
                allcolls = self.get_database().list_collection_names()
                includes = list(set(allcolls) - set(excludes))

                # dump each collection individually
                for coll in includes:
                    cmd = command + ['--collection', '%s' % coll]
                    dump_output = subprocess.check_output(cmd)
                logger.debug("db.py ::: dump - dump_output = %s" % dump_output)
            logger.info("mongodump ended.")
        except subprocess.CalledProcessError as msg:
            logger.error('COMMAND: %s'%(msg.cmd))
            logger.error('OUTPUT: %s'%(msg.output.decode('utf-8')))
            exitstatus = msg.returncode

        return exitstatus

    def restore(self, path, collection=None):
        '''
        Restore MongoDB
        Args:
            path (str): backup folder
            collection (str): if this is None, restore database. Otherwise, restore collection
        Returns:
            -
        '''
        logger.info("Starting mongorestore ...")
        exitstatus = 0

        command = [
            'mongorestore',
            '--host', '%s' % urlparse(self.db_uri).hostname,
            '-d', '%s' % self.database_name,
            '--port', '%s' % urlparse(self.db_uri).port,
            '--drop'
        ]

        if self.parsed_uri.get('username', None):
            command += ['-u', '%s' % self.parsed_uri.get('username')]
            command += ['-p', '%s' % self.parsed_uri.get('password')]

        if collection:
            command += ['--collection', '%s' % collection]
            pathname = os.sep.join([path, self.database_name, collection + '.bson'])
        else:
            pathname = os.sep.join([path, self.database_name])

        command += [pathname]
        logger.debug("db.py ::: restore - command = %s" % command)
        
        try:
            restore_output = subprocess.check_output(command)
            logger.debug("db.py ::: restore - restore_output = %s" % restore_output)
            logger.info("mongorestore ended")
        except subprocess.CalledProcessError as msg:
            logger.error(msg.cmd)
            logger.error(msg.output)
            exitstatus = msg.returncode

        return exitstatus

def get_db(request):
    return request.registry.settings['mongodb'].get_database()
