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

    var PREFIXES = {
            OU: 'ou_',
            USER: 'user_',
            GROUP: 'group_',
            COMPUTER: 'computer_',
            PRINTER: 'printer_',
            STORAGE: 'storage_'
        },
        MAX_LEVELS = 10,
        MAX_OBJECTS = 1000,
        MAX_NODES_PER_GROUP = 12,
        TYPES = ['ou', 'user', 'group', 'computer', 'printer', 'storage'],
        SEPARATOR = ',',
        GROUP_NESTED_PROBABILITY = 0.7,
        counters = {
            ous: 0,
            users: 0,
            groups: 0,
            computers: 0,
            printers: 0,
            storages: 0
        },
        potential_group_members = [],
        existing_groups = [],
        constructors = {},
        random_int,
        choice,
        object_creator,
        rootId,
        user_template,
        limit,
        user,
        ous,
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

        constructors[new_object_type](path);
    };

    constructors.ou = function (path) {
        var name = PREFIXES.OU + counters.ous,
            oid = new ObjectId(),
            new_children = random_int(MAX_LEVELS) + 1,
            h;

        counters.ous += 1;

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

        return oid;
    };

    constructors.user = function (path) {
        var name = PREFIXES.USER + counters.users,
            oid = new ObjectId();

        counters.users += 1;
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

        return oid;
    };

    constructors.group = function (path) {
        var oid = new ObjectId(),
            nodes_to_add = random_int(MAX_NODES_PER_GROUP),
            group = {
                '_id': oid,
                'path': path,
                'name': PREFIXES.GROUP + counters.groups,
                'nodemembers': [],
                'groupmembers': [],
                'type': 'group',
                'lock': false,
                'source': 'gecos'
            },
            count = 0,
            node_oid,
            parent_oid;

        counters.groups += 1;

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

        return oid;
    };

    constructors.computer = function (path) {
        var name = PREFIXES.COMPUTER + counters.computers,
            ip = random_int(256) + '.' + random_int(256) + '.' +
                random_int(256) + '.' + random_int(256),
            types = ['desktop', 'laptop', 'netbook', 'tablet'],
            oid = new ObjectId();

        counters.computers += 1;
        potential_group_members.push(oid);

        db.nodes.insert({
            '_id': oid,
            'path': path,
            'name': name,
            'type': 'computer',
            'lock': false,
            'source': 'gecos',
            'memberof': [],
            'identifier': 'id_' + name,
            'ip': ip,
            'mac': '98:5C:29:31:CF:07',
            'family': choice(types),
            'serial': 'SN' + random_int(100000),
            'registry': 'JDA' + random_int(10000),
            'extra': ''
        }, function (err, inserted) {
            print(inserted[0]._id);
        });

        return oid;
    };

    constructors.printer = function (path) {
        var name = PREFIXES.PRINTER + counters.printers,
            oid = new ObjectId();

        counters.printers += 1;
        potential_group_members.push(oid);

        db.nodes.insert({
            '_id': oid,
            'path': path,
            'name': name,
            'type': 'printer',
            'lock': false,
            'source': 'gecos',
            'memberof': []
        }, function (err, inserted) {
            print(inserted[0]._id);
        });

        return oid;
    };

    constructors.storage = function (path) {
        var name = PREFIXES.STORAGE + counters.storages,
            oid = new ObjectId();

        counters.storages += 1;
        potential_group_members.push(oid);

        db.nodes.insert({
            '_id': oid,
            'path': path,
            'name': name,
            'type': 'storage',
            'lock': false,
            'source': 'gecos',
            'memberof': []
        }, function (err, inserted) {
            print(inserted[0]._id);
        });

        return oid;
    };

    db.nodes.drop();

    rootId = constructors.ou('root'); // Populate the DB with the tree content
    while (db.nodes.count() < MAX_OBJECTS) {
        // Add more children to the root
        constructors.ou('root,' + rootId);
    }

    db.nodes.ensureIndex({'path': 1});
    db.nodes.ensureIndex({'type': 1});

    // Admin user generation

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
