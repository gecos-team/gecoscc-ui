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

    var MAX_LEVELS = 10,
        MAX_OBJECTS = 1000,
        MAX_NODES_PER_GROUP = 12,
        TYPES = ['ou', 'user', 'group', 'computer', 'printer', 'storage'],
        SEPARATOR = ',',
        GROUP_NESTED_PROBABILITY = 0.7,
        counters = {
            ou: 0,
            user: 0,
            group: 0,
            computer: 0,
            printer: 0,
            storage: 0
        },
        potential_group_members = [],
        existing_groups = [],
        constructors = {},
        random_int,
        choice,
        keys,
        each,
        defaults,
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

    keys = Object.keys || function (obj) {
        var result = [],
            key;
        if (obj !== Object.create(obj)) { throw new TypeError('Invalid object'); }
        for (key in obj) {
            if (obj.hasOwnProperty(key)) {
                result.push(key);
            }
        }
        return result;
    };

    each = function (obj, iterator, context) {
        var idx, length, breaker, keysAux;
        breaker = {};
        if (obj === null) { return; }
        if (Array.prototype.forEach && obj.forEach === Array.prototype.forEach) {
            obj.forEach(iterator, context);
        } else if (obj.length === +obj.length) {
            for (idx = 0, length = obj.length; idx < length; idx += 1) {
                if (iterator.call(context, obj[idx], idx, obj) === breaker) { return; }
            }
        } else {
            keysAux = keys(obj);
            for (idx = 0, length = keysAux.length; idx < length; i += 1) {
                if (iterator.call(context, obj[keysAux[idx]], keysAux[idx], obj) === breaker) { return; }
            }
        }
    };

    defaults = function (obj) {
        each(Array.prototype.slice.call(arguments, 1), function (source) {
            var prop;
            if (source) {
                for (prop in source) {
                    if (source.hasOwnProperty(prop)) {
                        if (obj[prop] === undefined) {
                            obj[prop] = source[prop];
                        }
                    }
                }
            }
        });
        return obj;
    };

    object_creator = function (path) {
        var new_object_type = choice(TYPES);

        if (db.nodes.count() >= MAX_OBJECTS ||
                (new_object_type === 'ou' && path.split(SEPARATOR).length >= MAX_LEVELS)) {
            return;
        }

        constructors[new_object_type](path);
    };

    constructors.default = function (path, type, extraValues) {
        var name = type + '_' + counters[type],
            oid = new ObjectId(),
            defs,
            values;

        counters[type] += 1;
        defs = {
            '_id': oid,
            'path': path,
            'name': name,
            'type': type,
            'lock': false,
            'source': 'gecos'
        };
        values = defaults(extraValues, defs);

        db.nodes.insert(values, function (err, inserted) {
            print(inserted[0]._id);
        });

        return oid;
    };

    constructors.ou = function (path) {
        var oid = constructors.default(path, 'ou', { 'policies': [] }),
            new_children = random_int(MAX_LEVELS) + 1,
            h;

        path = path + SEPARATOR + oid;
        // Add children to the OU
        for (h = 0; h < new_children; h += 1) {
            object_creator(path);
        }
        return oid;
    };

    constructors.user = function (path) {
        var email = 'user_' + counters.user + '@example.com',
            oid = constructors.default(path, 'user', { 'email': email });
        potential_group_members.push(oid);
        return oid;
    };

    constructors.group = function (path) {
        var oid = new ObjectId(),
            nodes_to_add = random_int(MAX_NODES_PER_GROUP),
            group = {
                '_id': oid,
                'path': path,
                'name': 'group_' + counters.group,
                'nodemembers': [],
                'groupmembers': [],
                'type': 'group',
                'lock': false,
                'source': 'gecos'
            },
            count = 0,
            node_oid,
            parent_oid;

        counters.group += 1;

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

        existing_groups.push(oid);

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
        var ip = random_int(256) + '.' + random_int(256) + '.' +
                random_int(256) + '.' + random_int(256),
            types = ['desktop', 'laptop', 'netbook', 'tablet'],
            oid;

        oid = constructors.default(path, 'computer', {
            'identifier': 'id_computer_' + counters.computer,
            'ip': ip,
            'mac': '98:5C:29:31:CF:07',
            'family': choice(types),
            'serial': 'SN' + random_int(100000),
            'registry': 'JDA' + random_int(10000),
            'extra': ''
        });
        potential_group_members.push(oid);
        return oid;
    };

    constructors.printer = function (path) {
        var oid = constructors.default(path, 'printer', {});
        potential_group_members.push(oid);
        return oid;
    };

    constructors.storage = function (path) {
        var ip = random_int(256) + '.' + random_int(256) + '.' +
                random_int(256) + '.' + random_int(256),
            protocols = ["ftp", "ssh", "nfs", "smb", "smb4"],
            oid;

        oid = constructors.default(path, 'storage', {
            server: ip,
            port: random_int(65535) + 1,
            protocol: choice(protocols),
            localpath: "/some/path/",
            mount: choice(["fstab", "gvfs"]),
            extraops: ""
        });
        potential_group_members.push(oid);
        return oid;
    };

    db.nodes.drop();

    rootId = constructors.ou('root'); // Populate the DB with the tree content
    while (db.nodes.count() < MAX_OBJECTS) {
        // Add more children to the root
        constructors.ou('root,' + rootId);
    }

    db.nodes.ensureIndex({ 'path': 1 });
    db.nodes.ensureIndex({ 'type': 1 });

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
