import pymongo

DEFAULT_MONGODB_HOST = 'localhost'
DEFAULT_MONGODB_PORT = 27017
DEFAULT_MONGODB_NAME = 'gecoscc'
DEFAULT_MONGODB_URI = 'mongodb://%s:%d/%s' % (DEFAULT_MONGODB_HOST,
                                              DEFAULT_MONGODB_PORT,
                                              DEFAULT_MONGODB_NAME)


class MongoDB(object):
    """Simple wrapper to get pymongo real objects from the settings uri"""

    def __init__(self, db_uri=DEFAULT_MONGODB_URI,
                 connection_factory=None, **kwargs):

        self.db_uri = db_uri

        if db_uri == "mongodb://":
            db_uri = DEFAULT_MONGODB_URI

        self.parsed_uri = pymongo.uri_parser.parse_uri(db_uri)

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
        db.nodes.ensure_index([
            ('path', pymongo.DESCENDING),
            ('type', pymongo.DESCENDING),
        ])


def get_db(request):
    return request.registry.settings['mongodb'].get_database()
