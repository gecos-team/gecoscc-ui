import scrypt
from uuid import uuid4

from pyramid.security import authenticated_userid


## MongoDB User Document structure
#  {
#   'username': 'user1',
#   'email': 'user1@example.com',
#   'apikey': ['123123123123'],
#   'password': {
#       'hash':'scrypt-hash',
#       'salt':'scrypt-salt'
#   }
#  }
#  ...
#

def generate_apikey():
    return uuid4()


def create_password(password):
    salt = uuid4().hex
    hash = scrypt.hash(password, salt)

    return {
        'hash': hash,
        'salt': salt
    }


def validate_password(password_dict, password):
    hash = scrypt.hash(password, password_dict['hash'])
    return (hash == password_dict['hash'])


class UserDoesNotExist(Exception):
    pass


class UserAlreadyExists(Exception):
    pass


class MongoUserDB(object):

    def __init__(self, mongo_connection, collection_name):
        self.db = mongo_connection.get_database()
        self.collection = self.db[collection_name]

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

    def check_password(self, username, password):
        user = self.get_user(username)
        password_dict = user.get('password', None)
        if password_dict is None:
            return False
        return validate_password(password_dict, password)

    def add_password(self, username, password):
        user = self.get_user(username)
        password_dict = create_password(password)
        self.collection.update({
            '_id': user['_id']
        }, {
            '$set': {
                'password': password_dict
            }
        })

    def create_user(self, username, password, email, extradata):
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


def get_userdb(request):
    return request.registry.settings['userdb']


def get_user(request):
    userid = authenticated_userid(request)
    if userid is not None:
        user = request.userdb.get_user(userid)
    else:
        if request.POST:
            apikey = request.POST.get('apikey')
        elif request.GET:
            apikey = request.GET.get('apikey')
        else:
            return None
        return request.userdb.get_user_by_apikey(apikey)

    return user
