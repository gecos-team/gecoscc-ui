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
    'use strict';

    var MAX_LEVELS = 6,
        MAX_CHILDS = 40,
        MAX_OBJECTS = 10000,
        MAX_GROUPS = 150,
        MAX_NODES_PER_GROUP = 15,
        MAX_GROUPS_PER_NODE = 8,
        MAX_POLICIES = 50,
        MAX_POLICIES_PER_NODE = 6,
        TYPES = ['ou', 'user', 'group', 'computer', 'printer', 'storage',
                 'repository'],

        SEPARATOR = ',',
        GROUP_NESTED_PROBABILITY = 0.4,
        POLICY_SCHEMA1,
        POLICY_SCHEMA2,
        POLICY_SCHEMAS,
        counters = {
            ou: 0,
            user: 0,
            group: 0,
            computer: 0,
            printer: 0,
            storage: 0,
            repository: 0
        },
        potential_group_members = [],
        existing_groups = [],
        constructors = {},
        random_int,
        choice,
        keys,
        each,
        contains,
        defaults,
        object_creator,
        somePolicies,
        policy,
        rootId,
        admin_user,
        limit,
        user,
        ous,
        ou,
        i,
        j;

    POLICY_SCHEMA1 = {
        "required": [
            "network_type"
        ],
        "type": "object",
        "properties": {
            "dns_server": {
                "title": "DNS Servers",
                "minItems": 1,
                "uniqueItems": true,
                "type": "array",
                "items": {
                    "type": "string"
                }
            },
            "network_type": {
                "title": "Network type",
                "pattern": "(wired|wireless)",
                "type": "string"
            },
            "netmask": {
                "title": "Netmask",
                "type": "string"
            },
            "use_dhcp": {
                "inlinetitle": "Use DHCP?",
                "type": "boolean"
            },
            "ip_address": {
                "title": "IP Address",
                "type": "string"
            },
            "gateway": {
                "title": "Gateway",
                "type": "string"
            }
        }
    };

    POLICY_SCHEMA2 = {
        "autostart_files": {
            "title": "Files to execute at booting",
            "minItems": 0,
            "uniqueItems": true,
            "type": "array",
            "items": {
                "required": [
                    "user",
                    "desktops"
                ],
                "type": "object",
                "properties": {
                    "desktops": {
                        "title": "Desktops",
                        "minItems": 0,
                        "uniqueItems": true,
                        "type": "array",
                        "items": {
                            "type": "string"
                        }
                    },
                    "user": {
                        "title": "Username",
                        "type": "string"
                    }
                }
            }
        }
    };


    POLICY_SCHEMAS = [POLICY_SCHEMA1, POLICY_SCHEMA2];

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

    contains = function (array, item) {
        var result = false;
        each(array, function (el) {
            result = result || el === item;
        });
        return result;
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
            return; // Abort
        }

        constructors[new_object_type](path);
    };

    somePolicies = function (type) {
        var policies = db.policies.find({ targets: { $all: [type] } }),
            toAdd = random_int(MAX_POLICIES_PER_NODE),
            result = {},
            idx,
            p;

        for (idx = 0; idx < toAdd; idx += 1) {
            p = policies[random_int(policies.count())];
            result[p._id.valueOf()] = {}; // <policy objId> = {<values>}
        }

        return result;
    };

    constructors.base = function (path, type, extraValues) {
        var name = type + '_' + counters[type],
            oid = new ObjectId(),
            defs,
            values;

        counters[type] += 1;
        defs = {
            _id: oid,
            path: path,
            name: name,
            type: type,
            lock: false,
            source: 'gecos'
        };
        values = defaults(extraValues, defs);

        db.nodes.insert(values, function (err, inserted) {
            print(inserted[0]._id);
        });

        return oid;
    };

    constructors.ou = function (path) {
        var oid = constructors.base(path, 'ou', {
                policies: somePolicies('ou'),
                extra: ''
            }),
            new_children = random_int(MAX_CHILDS) + 1,
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
            oid = constructors.base(path, 'user', {
                email: email,
                memberof: [],
                policies: somePolicies('user')
            });
        potential_group_members.push(oid);
        return oid;
    };

    constructors.group = function (path) {
        if (counters.group >= MAX_GROUPS) { return; }

        var oid = new ObjectId(),
            max_nodes_to_add = random_int(MAX_NODES_PER_GROUP),
            group = {
                _id: oid,
                path: path,
                name: 'group_' + counters.group,
                type: 'group',
                lock: false,
                source: 'gecos',
                members: [],
                memberof: [],
                policies: somePolicies('group')
            },
            count = 0,
            node_oid,
            parent_oid,
            l;

        counters.group += 1;

        if (existing_groups.length > 0 && Math.random() < GROUP_NESTED_PROBABILITY) {
            // This group is going to be a child of another group
            parent_oid = choice(existing_groups);
            group.memberof = [parent_oid];
            db.nodes.update({
                _id: parent_oid
            }, {
                $push: {
                    members: oid
                }
            });
        }

        existing_groups.push(oid);

        // Add some nodes to this group
        for (count; count < max_nodes_to_add; count += 1) {
            node_oid = choice(potential_group_members);
            if (node_oid) {
                l = db.nodes.findOne({ _id: node_oid }).memberof.length;
                if (l < MAX_GROUPS_PER_NODE && !contains(group.members, node_oid)) {
                    group.members.push(node_oid);
                    db.nodes.update({
                        _id: node_oid
                    }, {
                        $push: {
                            memberof: oid
                        }
                    });
                }
            }
        }

        db.nodes.insert(group, function (err, inserted) {
            print(inserted[0]._id);
        });

        return oid;
    };

    constructors.computer = function (path) {
        var types = ['desktop', 'laptop', 'netbook', 'tablet'],
            oid;

        oid = constructors.base(path, 'computer', {
            family: choice(types),
            registry: 'JDA' + random_int(10000),
            memberof: [],
            policies: somePolicies('computer')
        });
        potential_group_members.push(oid);
        return oid;
    };

    constructors.printer = function (path) {
        var brands = ['HP', 'Epson', 'Lexmark', 'Samsung', 'Canon', 'Brother'],
            brand,
            oid;

        brand = choice(brands);
        oid = constructors.base(path, 'printer', {
            brand: brand,
            model: brand.slice(0, 2).toUpperCase() + random_int(256),
            serial: brand.slice(0, 2).toUpperCase() + random_int(100000),
            registry: 'JDA' + random_int(10000),
            location: 'Dep' + random_int(999),
            printerpath: 'http://servidorimpresion:631/ipp/port' + random_int(65000),
            memberof: []
        });
        return oid;
    };

    constructors.storage = function (path) {
        var ip = random_int(256) + '.' + random_int(256) + '.' +
                random_int(256) + '.' + random_int(256),
            protocols = ['ftp', 'sshfs', 'nfs', 'smb', 'smb4'],
            oid;

        oid = constructors.base(path, 'storage', {
            connection_string: choice(protocols) + "://" + ip + ":" + (random_int(65535) + 1) + '/some/path/',
            memberof: []
        });
        return oid;
    };

    constructors.repository = function (path) {
        var urls = ['http://packages.linuxmint.com/pool/main/',
                    'http://packages.linuxmint.com/pool/upstream/',
                    'http://packages.linuxmint.com/pool/import/'],
            oid;

        oid = constructors.base(path, 'repository', {
            url: choice(urls)
        });
        return oid;
    };

    // Populate policies

    db.policies.drop();

    for (i = 0; i < MAX_POLICIES; i += 1) {
        policy = {
            _id: new ObjectId(),
            name: "Policy " + i,
            slug: "policy_" + i,
            schema: choice(POLICY_SCHEMAS),
            targets: [choice(TYPES.slice(0, 2))]
        };

        if (i % 2) {
            policy.targets.push(choice(TYPES.slice(2, 4)));
        }

        db.policies.insert(policy);
    }

    // Populate nodes

    db.nodes.drop();

    rootId = constructors.ou('root'); // Populate the DB with the tree content
    while (db.nodes.count() < MAX_OBJECTS) {
        // Add more children to the root
        constructors.ou('root,' + rootId);
    }

    db.nodes.ensureIndex({ path: 1 });
    db.nodes.ensureIndex({ type: 1 });

    // Admin user generation

    admin_user = {
        _id: new ObjectId(),
        username: 'admin',
        first_name: 'Ad',
        last_name: 'Min',
        password: '$2a$12$30QKDVBuIC8Ji4r5uXCjDehVdDI1ozCYyUiX6JHQ4iQB4n5DWZbsu',
        email: 'admin@example.com',
        permissions: [rootId]
    };

    db.adminusers.drop();
    db.adminusers.insert(admin_user);

    ous = db.nodes.find({ 'type': 'ou' });

    // Make the first 10 users admins of some OUs
    for (i = 0; i < 10; i += 1) {
        user = {};
        user.username = 'admin_user_' + i;
        user.first_name = 'admin first name' + i;
        user.last_name = 'admin last name' + i;
        user.email = 'user' + i + '@example.com';
        user.permissions = [];
        user.password = '$2a$12$30QKDVBuIC8Ji4r5uXCjDehVdDI1ozCYyUiX6JHQ4iQB4n5DWZbsu';
        user._id = new ObjectId();

        limit = random_int(10);
        for (j = 0; j < limit; j += 1) {
            ou = ous[random_int(ous.count())];
            user.permissions.push(ou._id);
        }
        db.adminusers.insert(user);
    }
}(ObjectId, db, print));
