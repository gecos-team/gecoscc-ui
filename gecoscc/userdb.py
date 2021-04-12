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

from uuid import uuid4
import bcrypt
import pymongo


## MongoDB User Document structure
#  {
#   'username': 'user1',
#   'email': 'user1@example.com',
#   'apikey': ['123123123123'],
#   'password': 'password-bcrypt-hash',
#  }
#  ...
#

def generate_apikey():
    return uuid4().hex


def create_password(password):
    hashval = bcrypt.hashpw(password, bcrypt.gensalt())
    return hashval


def validate_password(password_hash, password):
    hashval = bcrypt.hashpw(password,
                         password_hash)
    return hashval == password_hash


class UserDoesNotExist(Exception):
    pass


class UserAlreadyExists(Exception):
    pass


class MongoUserDB:

    def __init__(self, mongo_connection, collection_name):
        self.mongo_connection = mongo_connection
        self.collection_name = collection_name
        self.db = None        

    def ensure_connection(self):
        if self.db is None:
            self.db = self.mongo_connection.get_database()
            self.collection = self.db[self.collection_name]
            self.indexes()
            

    def indexes(self):
        self.db.adminusers.create_index([
            ('username', pymongo.DESCENDING),
        ], unique=True)

        self.db.adminusers.create_index([
            ('email', pymongo.DESCENDING),
        ], unique=True)

    def get_user(self, username):
        self.ensure_connection()
        user = self.collection.find_one({'username': username})
        if not user:
            raise UserDoesNotExist()
        return user

    def get_user_by_apikey(self, apikey):
        self.ensure_connection()
        user = self.collection.find_one({'apikey': apikey})
        if not user:
            raise UserDoesNotExist()
        return user

    def login(self, username, password):
        self.ensure_connection()
        user = self.get_user(username)
        password_dict = user.get('password', None)
        if password_dict is None:
            return False
        
        if validate_password(password_dict, password):
            return user
        
        return False

    def change_password(self, username, password):
        self.ensure_connection()
        user = self.get_user(username)
        password_hash = create_password(password)
        self.collection.update_one({
            '_id': user['_id']
        }, {
            '$set': {
                'password': password_hash
            }
        })

    def create_user(self, username, password, email, extradata={}):
        self.ensure_connection()
        # Test if the username was not registered before
        user = self.collection.find_one({'username': username})
        if user is not None:
            raise UserAlreadyExists()

        # Test if the email was not registered before
        user = self.collection.find_one({'email': email})
        if user is not None:
            raise UserAlreadyExists()

        user = extradata

        user.update({
            'username': username,
            'email': email,
            'password': create_password(password),
            'apikey': [self.create_unique_apikey()],
        })

        self.collection.insert_one(user)

    def create_unique_apikey(self):
        self.ensure_connection()
        while True:
            new_apikey = generate_apikey()
            try:
                self.get_user_by_apikey(new_apikey)
            except UserDoesNotExist:
                return new_apikey

    def add_apikey(self, username, _apikey):
        self.ensure_connection()
        self.collection.update_one({
            'username': username
        }, {
            '$push': {
                'apikey': self.create_unique_apikey()
            }
        })

    def count_users(self, filters=None):
        self.ensure_connection()
        return self.collection.count_documents(filters)

    def list_users(self, filters=None):
        self.ensure_connection()
        return self.collection.find(filters)

    def delete_user(self, filters=None):
        self.ensure_connection()
        return self.collection.delete_one(filters)


def get_userdb(request):
    return request.registry.settings['userdb']


def get_user(request):
    userid = request.authenticated_userid
    if userid is not None:
        return request.userdb.get_user(userid)

    if request.POST:
        apikey = request.POST.get('apikey')
    elif request.GET:
        apikey = request.GET.get('apikey')
    else:
        return None

    if apikey:
        return request.userdb.get_user_by_apikey(apikey)

    return None


def get_groups(userid, request):
    ## TODO
    # Not Implemented
    user = request.userdb.get_user(userid)
    if user.get('is_superuser',None):
        return ['logged', 'g:maintenance']
    return ['logged']
