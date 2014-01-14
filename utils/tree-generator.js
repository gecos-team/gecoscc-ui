/*jslint vars: false, nomen: true, unparam: true */
/*global ObjectId, db, print */

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

(function (ObjectId, db, print) {
    "use strict";

    var OU_PREFIX = 'ou_',
        USER_PREFIX = 'user_',
        GROUP_PREFIX = 'group_',
        MAX_LEVELS = 10,
        MAX_OBJECTS = 1000,
        MAX_NODES_PER_GROUP = 12,
        TYPES = ['ou', 'user', 'group'],
        SEPARATOR = ',',
        GROUP_NESTED_PROBABILITY = 0.7,
        users = 0,
        ous = 0,
        groups = 0,
        potential_group_members = [],
        existing_groups = [],
        random_int,
        choice,
        object_creator,
        ou_creator,
        user_creator,
        types_creator,
        group_creator,
        user_template,
        limit,
        user,
        ou,
        i,
        j;

    random_int = function (max) {
        return Math.floor(Math.random() * max);
    };

    choice = function (l) {
        return l[random_int(l.length)];
    };

    object_creator = function (path) {
        var new_object_type = choice(TYPES);

        if (db.nodes.count() >= MAX_OBJECTS ||
                (new_object_type === 'ou' && path.split(SEPARATOR).length >= MAX_LEVELS)) {
            return;
        }

        types_creator[new_object_type](path);
    };

    ou_creator = function (path) {
        var name = OU_PREFIX + ous,
            oid = new ObjectId(),
            new_children = random_int(MAX_LEVELS) + 1,
            h;

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
            print(inserted[0]._id);
        });

        path = path + SEPARATOR + oid;

        // Add children to the OU
        for (h = 0; h < new_children; h += 1) {
            object_creator(path);
        }

    };

    user_creator = function (path) {
        var name = USER_PREFIX + users,
            oid = new ObjectId();

        users += 1;
        potential_group_members.push(oid);

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
            print(inserted[0]._id);
        });
    };

    group_creator = function (path) {
        var oid = new ObjectId(),
            nodes_to_add = random_int(MAX_NODES_PER_GROUP),
            group = {
                '_id': oid,
                'path': path,
                'name': GROUP_PREFIX + groups,
                'nodemembers': [],
                'groupmembers': [],
                'type': 'group',
                'lock': false,
                'source': 'gecos'
            },
            count = 0,
            node_oid,
            parent_oid;

        groups += 1;

        if (Math.random() > GROUP_NESTED_PROBABILITY) {
            // This group is going to be a child of another group
            parent_oid = random_int(existing_groups.length);
            parent_oid = existing_groups[parent_oid];
            group.memberof = parent_oid;
            db.nodes.update({
                '_id': parent_oid
            }, {
                '$push': {
                    'groupmembers': oid
                }
            });
        }

        // Add some nodes to this group
        for (count; count < nodes_to_add; count += 1) {
            node_oid = random_int(potential_group_members.length);
            node_oid = potential_group_members[node_oid];
            group.nodemembers.push(node_oid);
            db.nodes.update({
                '_id': node_oid
            }, {
                '$push': {
                    'memberof': oid
                }
            });
        }

        db.nodes.insert(group, function (err, inserted) {
            print(inserted[0]._id);
        });
    };

    types_creator = {
        'ou': ou_creator,
        'user': user_creator,
        'group': group_creator
    };

    db.nodes.drop();

    ou_creator('root'); // Populate the DB with the tree content

    db.nodes.ensureIndex({'path': 1});
    db.nodes.ensureIndex({'type': 1});


    /* adminuser generation */

    user_template = {
        "_id": new ObjectId("527a325cbd4d720d3ab11025"),
        "username": "admin",
        "password": "$2a$12$30QKDVBuIC8Ji4r5uXCjDehVdDI1ozCYyUiX6JHQ4iQB4n5DWZbsu",
        "email": "admin@example.com",
        "permissions": ["root,"]
    };

    db.adminusers.drop();
    db.adminusers.insert(user_template);

    ous = db.nodes.find({ 'type': 'ou' });

    // Make the first 10 users admins of some OUs
    for (i = 0; i < 10; i += 1) {
        user = user_template;
        user.username = 'user_' + i;
        user.email = 'user' + i + '@example.com';
        user.permissions = [];
        user._id = new ObjectId();

        limit = random_int(10);
        for (j = 0; j < limit; j += 1) {
            ou = ous[random_int(ous.count())];
            user.permissions.push(ou._id);
        }
        db.adminusers.insert(user);
    }
}(ObjectId, db, print));
