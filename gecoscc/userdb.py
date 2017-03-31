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

import bcrypt
from uuid import uuid4
import pymongo
from pyramid.security import authenticated_userid
from pyramid.threadlocal import get_current_registry
import ldap

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
    hash = bcrypt.hashpw(password, bcrypt.gensalt())
    return hash


def validate_password(password_hash, password):
    hash = bcrypt.hashpw(password,
                         password_hash)
    return (hash == password_hash)


class UserDoesNotExist(Exception):
    pass


class UserAlreadyExists(Exception):
    pass


class MongoUserDB(object):

    def __init__(self, mongo_connection, collection_name):
        self.db = mongo_connection.get_database()
        self.collection = self.db[collection_name]
        self.indexes()

    def indexes(self):

        self.db.adminusers.ensure_index([
            ('username', pymongo.DESCENDING),
        ], unique=True)

        self.db.adminusers.ensure_index([
            ('email', pymongo.DESCENDING),
        ], unique=True)

    def get_user(self, username):
        user = self.collection.find_one({'username': username})
        if not user:
            raise UserDoesNotExist()
        return user

    def get_user_by_apikey(self, apikey):
        user = self.collection.find_one({'apikey': apikey})
        if not user:
            raise UserDoesNotExist()
        return user

    def get_authtype(self, username):
        user_authtype = self.collection.find_one({'username': username},{'authtype': 1})
        if not user_authtype:
            raise UserDoesNotExist()
        return user_authtype

    def login(self, username, password, authtype):
        user = self.get_user(username)
        password_dict = user.get('password', None)
        authtype = str(authtype)

        if authtype == 'ldap':
            return get_ldap_auth(str(user['username']),password)
        else:
            if password_dict is None:
                return False
            if validate_password(password_dict, password):
                return user
            else:
                return False

    def change_password(self, username, password):
        user = self.get_user(username)
        password_hash = create_password(password)
        self.collection.update({
            '_id': user['_id']
        }, {
            '$set': {
                'password': password_hash
            }
        })

    def create_user(self, username, password, email, extradata={}):
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

        self.collection.save(user)

    def create_unique_apikey(self):
        while True:
            new_apikey = generate_apikey()
            try:
                self.get_user_by_apikey(new_apikey)
            except UserDoesNotExist:
                return new_apikey

    def add_apikey(self, username, apikey):
        self.collection.update({
            'username': username
        }, {
            '$push': {
                'apikey': self.create_unique_apikey()
            }
        })

    def add_authtype(self, username):
        self.collection.update({
            'username': username
        }, {
            '$set': {
                'authtype': 'local'
            }
        })

    def list_users(self, filters=None):
        return self.collection.find(filters)

    def delete_users(self, filters=None):
        return self.collection.remove(filters)


def get_userdb(request):
    return request.registry.settings['userdb']


def get_user(request):
    userid = request.authenticated_userid
    if userid is not None:
        return request.userdb.get_user(userid)
    else:
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
    return ['logged']

def get_ldap_info():
    settings = get_current_registry().settings
    ldap = {
        'url' : settings.get('gecos.ldap.url'),
        'port': settings.get('gecos.ldap.port'),
        'prfx': settings.get('gecos.ldap.prfx'),
        'base': settings.get('gecos.ldap.base')
    }
    return ldap

def get_ldap_auth(user,password):
    ldap_info = get_ldap_info()
    conn = str(ldap_info['url'])+':'+str(ldap_info['port'])
    conn = conn.replace('"','')
    basedn = str(ldap_info['prfx'])+user+","+str(ldap_info['base'])
    basedn = basedn.replace('"','')

    ld = ldap.initialize(conn)

    try:
        ld.simple_bind_s(basedn,password)
        result = ld.whoami_s()
        ld.unbind_s()
        return result
    except ldap.LDAPError, e:
        ld.unbind_s()
        return False

