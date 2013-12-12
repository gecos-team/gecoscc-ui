var ou_prefix = 'ou_',
    user_prefix = 'user_',
    group_prefix = 'group_',
    users = 0,
    ous = 0,
    groups = 0,
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

    group_creator = function(name, maxlevel) {
        var parent_id = arguments[2],
            children_counter = random_int(max_levels) + 1,
            nodes = random_int(max_levels) + 1,
            max_node_id = db.nodes.find({'type': 'user'}).count(),
            group = {
                '_id': ObjectId(),
                'name': name,
            }

        if (parent_id !== undefined) {
            group.memberof = parent_id;
            db.groups.update({
                    '_id': parent_id,
            }, {
                '$push': {
                    'groupmembers': group['_id']
                }
            });
        }

        group['nodemembers'] = [];
        // insert groups in nodes (two ways relation)
        for(var n = 0; n<nodes; n += 1) {
            var node_suffix = random_int(max_node_id),
                node_name = user_prefix + node_suffix;
            node = db.nodes.findOne({'name': node_name});
            group['nodemembers'].push(node['_id']);
            db.nodes.update({
                '_id': node['_id']
            }, {
                '$push': {
                    'memberof': group['_id']
                }
            });
        }

        db.groups.insert(group);

        if (maxlevel > 0) {
            for(children_counter=children_counter;
                    children_counter >0;
                    children_counter -= 1) {
               groups += 1;
               group_creator(group_prefix + groups, maxlevel-1, group._id);
            }
        }

    }

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
            'policies': [],
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
            'memberof': [],
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

group_creator(group_prefix + db.groups.count(), 3);
group_creator(group_prefix + db.groups.count(), 2);
group_creator(group_prefix + db.groups.count(), 1);
group_creator(group_prefix + db.groups.count(), 3);

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
