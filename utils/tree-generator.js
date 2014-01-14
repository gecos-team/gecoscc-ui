/*jslint vars: false, nomen: true, unparam: true */
/*global ObjectId, db */

// Copyright 2014 Junta de Andalucia
//
// Licensed under the EUPL, Version 1.1 or - as soon they
// will be approved by the European Commission - subsequent
// versions of the EUPL (the "Licence");
// You may not use this work except in compliance with the
// Licence.
// You may obtain a copy of the Licence at:
//
// http://ec.europa.eu/idabc/eupl
//
// Unless required by applicable law or agreed to in
// writing, software distributed under the Licence is
// distributed on an "AS IS" basis,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either
// express or implied.
// See the Licence for the specific language governing
// permissions and limitations under the Licence.

(function (ObjectId, db) {
    "use strict";

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
        random_int,
        choice,
        object_creator,
        ou_creator,
        user_creator,
        types_creator,
        group_creator,
        user_template,
        i,
        ou,
        user,
        j;

    random_int = function (max) {
        return Math.floor(Math.random() * max);
    };

    choice = function (l) {
        return l[random_int(l.length)];
    };

    object_creator = function (path) {
        var new_object_type = choice(types);

        if (db.nodes.count() >= max_objects) {
            return;
        }

        if ((new_object_type === 'ou' &&
                path.split(separator).length < max_levels) ||
                new_object_type === 'user') {
            children = types_creator[new_object_type](path);
        }
    };

    ou_creator = function (path) {
        var name = ou_prefix + ous,
            oid = new ObjectId(),
            new_children = random_int(max_levels) + 1,
            idx;

        ous += 1;

        db.nodes.insert({
            '_id': oid,
            'path': path,
            'name': name,
            'type': 'ou',
            'lock': false,
            'source': 'gecos',
            'policies': []
        }, function (err, inserted) {
            inserted[0]._id;
        });

        path = path + separator + oid;

        for (idx = 0; idx < new_children; idx += 1) {
            object_creator(path);
        }

    };

    user_creator = function (path) {
        var name = user_prefix + users,
            oid = new ObjectId();
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
            inserted[0]._id;
        });
    };

    types_creator = {
        'ou': ou_creator,
        'user': user_creator
    };

    group_creator = function (name, maxlevel, parent_id) {
        var children_counter = random_int(max_levels) + 1,
            nodes = random_int(max_levels) + 1,
            max_node_id = db.nodes.find({'type': 'user'}).count(),
            group = {
                '_id': new ObjectId(),
                'name': name
            },
            node_suffix,
            node_name,
            node,
            n,
            counter;

        if (!db.groups.findOne({ name: name })) {
            if (parent_id !== undefined) {
                group.memberof = parent_id;
                db.groups.update({
                    '_id': parent_id
                }, {
                    '$push': {
                        'groupmembers': group._id
                    }
                });
            }

            group.nodemembers = [];

            // insert groups in nodes (two ways relation)
            for (n = 0; n < nodes; n += 1) {
                node_suffix = random_int(max_node_id);
                node_name = user_prefix + node_suffix;
                node = db.nodes.findOne({ 'name': node_name });
                group.nodemembers.push(node._id);
                db.nodes.update({
                    '_id': node._id
                }, {
                    '$push': {
                        'memberof': group._id
                    }
                });
            }

            db.groups.insert(group);

            if (maxlevel > 0) {
                for (counter = children_counter; counter > 0; counter -= 1) {
                    groups += 1;
                    group_creator(group_prefix + groups, maxlevel - 1, group._id);
                }
            } else {
                groups += 1;
            }
        }
    };

    db.nodes.drop();
    db.groups.drop();

    ou_creator('root');

    group_creator(group_prefix + db.groups.count(), 3);
    group_creator(group_prefix + db.groups.count(), 2);
    group_creator(group_prefix + db.groups.count(), 1);
    group_creator(group_prefix + db.groups.count(), 3);

    db.nodes.ensureIndex({'path': 1});
    db.nodes.ensureIndex({'type': 1});


    /* adminuser generation */

    user_template = {
        "_id": new ObjectId("527a325cbd4d720d3ab11025"),
        "username": "admin",
        "password": "$2a$12$NNyrOEYPdBu4OApMpfeYfu/GArui2yLVJPIyglPIgPKT03sOHTCGy",
        "email": "admin@example.com",
        "permissions": ["root,"]
    };

    db.adminusers.drop();

    db.adminusers.insert(user_template);

    ous = db.nodes.find({ 'type': 'ou' });

    for (i = 0; i < 10; i += 1) {
        user = user_template;
        user.username = 'user_' + i;
        user.email = 'user' + i + '@example.com';
        user.permissions = [];
        user._id = new ObjectId();

        for (j = 0; j < random_int(10); j += 1) {
            ou = ous[random_int(ous.count())];
            user.permissions.push(ou._id);
        }
        db.adminusers.insert(user);
    }
}(ObjectId, db));
