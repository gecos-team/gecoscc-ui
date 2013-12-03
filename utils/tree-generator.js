var ou_prefix = 'ou_',
    user_prefix = 'user_'
    users = 0,
    ous = 0,
    types = ['ou', 'user'],
    max_levels = 10,
    max_objects = 1000,
    separator = ',',
    generic_group_oid = ObjectId(),

    random_int = function (max) {
        return Math.floor(Math.random() * max)
    },

    choice = function(l) {
        return l[random_int(l.length)]
    },

    object_creator = function (path) {
        var new_object_type = choice(types);

        if (db.nodes.count() >= max_objects) {
            return
        }

        if ((new_object_type == 'ou' &&
                path.split(separator).length < max_levels) ||
                new_object_type == 'user') {
            children = types_creator[new_object_type](path);
        }
    },

    ou_creator = function (path) {
        var name = ou_prefix + ous,
            oid = ObjectId(),
            new_children = random_int(max_levels) + 1;
        ous += 1;

        db.nodes.insert({
            '_id': oid,
            'path': path,
            'name': name,
            'type': 'ou',
            'lock': false,
            'source': 'gecos',
        }, function (err, inserted) {
            inserted[0]._id
        });

        path = path + separator + oid;

        for (var i=0; i < new_children; i+=1) {
            object_creator(path);
        }

    },

    user_creator = function (path) {
        var name = user_prefix + users,
            oid = ObjectId();
        users += 1;

        db.nodes.insert({
            '_id': oid,
            'path': path,
            'name': name,
            'type': 'user',
            'lock': false,
            'source': 'gecos',
            'groups': [{
                '_id':generic_group_oid,
                'name':'generic-group'
            }],
            'email': name + '@example.com'
        }, function (err, inserted) {
            inserted[0]._id
        });

    },

    types_creator = {
        'ou': ou_creator,
        'user': user_creator
    };


db.nodes.drop();

ou_creator('root');

db.nodes.ensureIndex({'path': 1});
db.nodes.ensureIndex({'type': 1});


/* adminuser generation */

user_template = {
    "_id": ObjectId("527a325cbd4d720d3ab11025"),
    "username": "admin",
    "password": "$2a$12$NNyrOEYPdBu4OApMpfeYfu/GArui2yLVJPIyglPIgPKT03sOHTCGy",
    "apikey": ["638cc54845864082a2c1513e7a17e933"],
    "email": "admin@example.com",
    "permissions": ["root,"]
};

db.adminusers.drop();

db.adminusers.insert(user_template);

ous = db.nodes.find({'type': 'ou'})

for (var i=0; i<10; i+=1) {
    var permissions = [],
        user = user_template;
    user['username'] = 'user_' + i;
    user['email'] = 'user' + i + '@example.com';
    user['permissions'] = [];
    user['_id'] = ObjectId();

    for (var j=0; j<random_int(10); j+=1) {
        ou = ous[random_int(ous.count())];
        user['permissions'].push(ou['_id']);
    }
    db.adminusers.insert(user);
}
