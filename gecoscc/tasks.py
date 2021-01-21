#
# Copyright 2013, Junta de Andalucia
# http://www.juntadeandalucia.es/
#
# Authors:
#   Pablo Martin <goinnn@gmail.com>
#   Pablo Iglesias <pabloig90@gmail.com>
#
# All rights reserved - EUPL License V 1.1
# https://joinup.ec.europa.eu/software/page/eupl/licence-eupl
#

from six import text_type
import datetime
import random
import os
import re
import subprocess
import traceback
import sys
import shutil
import time

from glob import glob
from copy import deepcopy
from bson import ObjectId

from chef import Node, Client
from chef.node import NodeAttributes

from celery.task import Task, task
from celery.signals import task_prerun
from celery.exceptions import Ignore
from jsonschema import validate
from jsonschema.exceptions import ValidationError
from pyramid.threadlocal import get_current_registry

import gettext
from gecoscc.models import User

from gecoscc.eventsmanager import JobStorage
from gecoscc.rules import get_rules, is_user_policy, get_username_chef_format, object_related_list
from gecoscc.socks import invalidate_jobs, update_tree, invalidate_change, add_computer_to_user

# Ignore unused import warning on "apply_policies_to_*" functions because 
# "object_moved" function calls them

from gecoscc.utils import (get_chef_api, get_cookbook,
                           get_filter_nodes_belonging_ou, get_filter_in_domain,
                           emiter_police_slug, get_computer_of_user,
                           delete_dotted, to_deep_dict, reserve_node_or_raise,
                           save_node_and_free, NodeBusyException, NodeNotLinked,
                           apply_policies_to_user, apply_policies_to_computer, apply_policies_to_group, apply_policies_to_ou,
                           apply_policies_to_printer, apply_policies_to_storage, apply_policies_to_repository,
                           remove_policies_of_computer, recursive_defaultdict, setpath, dict_merge, nested_lookup,
                           RESOURCES_RECEPTOR_TYPES, RESOURCES_EMITTERS_TYPES, POLICY_EMITTER_SUBFIX,
                           get_policy_emiter_id, get_object_related_list, update_computers_of_user, trace_inheritance,
                           order_groups_by_depth, order_ou_by_depth, move_in_inheritance_and_recalculate_policies,
                           recalculate_inherited_field, remove_group_from_inheritance_tree, add_group_to_inheritance_tree,
                           recalculate_inheritance_for_node, get_filter_ous_from_path, recalculate_policies_for_computers,
                           add_path_attrs_to_node, setPathAttrsToNodeException)


DELETED_POLICY_ACTION = 'deleted'
ORDER_BY_TYPE_ASC = ('ou','group','computer','user')
USERS_OHAI = 'ohai_gecos.users'

class ChefTask(Task):
    abstract = True
    # Since Celery 4 the default serializer is "json", but we need "pickle"
    serializer = 'pickle'
    
    def __init__(self):
        self.init_jobid()
        self.logger = self.get_logger()
        localedir = os.path.join(os.path.dirname(__file__), 'locale')
        gettext.bindtextdomain('gecoscc', localedir)
        gettext.textdomain('gecoscc')
        self._ = gettext.gettext
        
    @property
    def db(self):
        if hasattr(self, '_db'):
            return self._db
        return get_current_registry().settings.get(
            'mongodb').get_database()

    def log(self, messagetype, message):
        assert messagetype in ('debug', 'info', 'warning', 'error', 'critical')
        op = getattr(self.logger, messagetype)
        op('[{0}] {1}'.format(self.jid, message))

    def on_failure(self, exc, task_id, args, kwargs, einfo):
        self.log('error', ''.join(traceback.format_exception(
            etype=type(exc), value=exc, tb=einfo.tb)))
        super(ChefTask, self).on_failure(exc, task_id, args, kwargs, einfo)

    def init_jobid(self):
        if getattr(self, 'request', None) is not None:
            self.jid = self.request.id
        else:
            self.jid = text_type(ObjectId())

    def walking_here(self, obj, related_objects):
        '''
        Checks if an object is in the object related list else add it to the list
        '''
        if related_objects is not None:
            if obj not in related_objects:
                related_objects.append(deepcopy(obj))
            else:
                return True
        return False

    def get_related_computers_of_computer(self, obj, related_computers, related_objects):
        '''
        Get the related computers of a computer
        '''
        if self.walking_here(obj, related_objects):
            return related_computers
        related_computers.append(obj)
        return related_computers

    def get_related_computers_of_group(self, obj, related_computers, related_objects):
        '''
        Get the related computers of a group
        '''
        if self.walking_here(obj, related_objects):
            return related_computers
        for node_id in obj['members']:
            node = self.db.nodes.find_one({'_id': node_id})
            if node and node not in related_objects:
                self.get_related_computers(node, related_computers, related_objects)
        return related_computers

    def get_related_computers_of_ou(self, ou, related_computers, related_objects):
        '''
        Get the related computers of an OU
        '''
        if self.walking_here(ou, related_objects):
            return related_computers
        computers = self.db.nodes.find({'path': get_filter_nodes_belonging_ou(ou['_id']),
                                        'type': 'computer'})
        for computer in computers:
            self.get_related_computers_of_computer(computer,
                                                   related_computers,
                                                   related_objects)

        users = self.db.nodes.find({'path': get_filter_nodes_belonging_ou(ou['_id']),
                                    'type': 'user'})
        for user in users:
            self.get_related_computers_of_user(user,
                                               related_computers,
                                               related_objects)

        groups = self.db.nodes.find({'path': get_filter_nodes_belonging_ou(ou['_id']),
                                     'type': 'group'})
        for group in groups:
            self.get_related_computers_of_group(group,
                                                related_computers,
                                                related_objects)

        return related_computers

    def get_related_computers_of_emiters(self, obj, related_computers, related_objects):
        '''
        Get the related computers of emitter objects
        '''
        if self.walking_here(obj, related_objects):
            return related_computers
        object_related_list = get_object_related_list(self.db, obj)
        for object_related in object_related_list:
            self.get_related_computers(object_related, related_computers, related_objects)
        return related_computers

    def get_related_computers_of_user(self, obj, related_computers, related_objects):
        '''
        Get the related computer of User
        '''
        if self.walking_here(obj, related_objects):
            return related_computers
        return get_computer_of_user(self.db.nodes, obj, related_computers)

    def get_related_computers(self, obj, related_computers=None, related_objects=None):
        '''
        Get the related computers with the objs
        '''
        if related_objects is None:
            related_objects = []

        if related_computers is None:
            related_computers = []

        obj_type = obj['type']

        if obj['type'] in RESOURCES_EMITTERS_TYPES:
            obj_type = 'emiters'
        get_realted_computers_of_type = getattr(self, 'get_related_computers_of_%s' % obj_type)
        return get_realted_computers_of_type(obj, related_computers, related_objects)

    def is_updating_policies(self, obj, objold):
        '''
        Checks if the not mergeable policy has changed or is equal to the policy stored in the node chef.
        '''
        new_policies = obj.get('policies', {})
        new_memberof = obj.get('memberof', {})
        if objold is None:
            old_policies = {}
            old_memberof = {}
        else:
            old_policies = objold.get('policies', {})
            old_memberof = objold.get('memberof', {})
        return new_policies != old_policies or new_memberof != old_memberof

    def is_updated_node(self, obj, objold):
        '''
        Chef if an objects is updated in node
        '''
        return obj != objold

    def get_object_ui(self, rule_type, obj, node, policy):
        '''
        Get the object
        '''
        if obj == {}:
            return {}
        if rule_type == 'save':
            self.log("info","tasks:::get_object_ui rule_type='save' is_emitter_policy=%s"%(policy.get('is_emitter_policy', False)))
            #if policy.get('is_emitter_policy', False):
            #    obj = self.db.nodes.find_one({'node_chef_id': node.name})
            self.log("info","tasks:::get_object_ui obj['type']=%s"%(obj['type']))
            return obj
        elif rule_type == 'policies':
            policy_id = text_type(policy['_id'])
            if policy.get('is_emitter_policy', False):
                if not obj.get(rule_type, None):
                    object_related_id_list = []
                else:
                    object_related_id_list = obj[rule_type].get(policy_id,{}).get('object_related_list',[])
                object_related_list = []
                for object_related_id in object_related_id_list:
                    object_related = self.db.nodes.find_one({'_id': ObjectId(object_related_id)})
                    if not object_related:
                        continue
                    object_related_list.append(object_related)
                return {'object_related_list': object_related_list,
                        'type': policy['slug'].replace(POLICY_EMITTER_SUBFIX, '')}
            else:
                try:
                    return obj[rule_type][policy_id]
                except KeyError:
                    return {}
        return ValueError("The rule type should be save or policy")

    def get_rules_and_object(self, rule_type, obj, node, policy):
        '''
        Get the rules and object
        '''
        if rule_type == 'save':
            rules = get_rules(obj['type'], rule_type, node, policy)
            obj = self.get_object_ui(rule_type, obj, node, policy)
            if not obj:
                rules = {}
            return (rules, obj)
        elif rule_type == 'policies':
            rules = get_rules(obj['type'], rule_type, node, policy)
            return (rules,
                    self.get_object_ui(rule_type, obj, node, policy))
        return ValueError("The rule type should be save or policy")

    def get_related_objects(self, nodes_ids, policy, obj_type):
        '''
        Get related objects from a emitter policy
        '''
        new_field_chef_value = []
        updater_nodes = self.db.nodes.find({"$or": [{'_id': {"$in": nodes_ids}}]})

        for updater_node in updater_nodes:
            if text_type(policy['_id']) in updater_node['policies']:
                new_field_chef_value += updater_node['policies'][text_type(policy['_id'])]['object_related_list']

        new_field_chef_value = list(set(new_field_chef_value))
        self.log("debug","tasks.py:::get_related_objects -> new_field_chef_value = {0}".format(new_field_chef_value))
        related_objects = []

        for node_id in new_field_chef_value:
            related_objs = self.db.nodes.find_one({'_id': ObjectId(node_id)})
            obj_list = {'object_related_list': [related_objs], 'type': obj_type}
            related_objects += object_related_list(obj_list)
        self.log("debug","tasks.py:::get_related_objects -> related_objects = {0}".format(related_objects))
        return related_objects

    def get_nodes_ids(self, nodes_updated_by):
        '''
        Get the nodes ids
        '''
        nodes_ids = []
        for _node_type, updated_by_id in nodes_updated_by:
            if isinstance(updated_by_id, list):
                nodes_ids += [ObjectId(node_id) for node_id in updated_by_id]
            else:
                nodes_ids.append(ObjectId(updated_by_id))
        return nodes_ids

    def remove_duplicated_dict(self, new_field_chef_value):
        '''
        Remove duplicate elements from a list of dictionaries
        '''
        new_field_chef_dict = []
        for field_value in new_field_chef_value:
            if field_value not in new_field_chef_dict:
                new_field_chef_dict.append(field_value)

        return new_field_chef_dict

    def has_changed_ws_policy(self, node, obj_ui_field, objold_ui_field, field_chef):
        '''
        This method checks whether the "field_chef" policy field changed for the current object.

        Args:
            node (ChefNode): reserved node in Chef, receiver the policy.

            field_chef (str): policy field path. Example: gecos_ws_mgmt.software_mgmt.package_res.package_list

            obj_ui_field (list): value of policy field in object after current executed action.
                                 Example: [{'name':'evince','version':'current','action':'add'},{'name':'xournal','version':'latest','action':'add'}]

            objold_ui_field (list): value of policy field in object before current executed action 
                                    Example: [{'name':'evince','version':'current','action':'remove'},{'name':'xournal','version':'latest','action':'add'}])

        Returns:
            bool:  True if policy field changed and its value not in stored value in Chef node. False otherwise. 
        '''
        self.log("info","tasks.py ::: Starting has_changed_ws_policy method ...")
        self.log("debug","tasks.py ::: has_changed_ws_policy - obj_ui_field = {0}".format(obj_ui_field))
        self.log("debug","tasks.py ::: has_changed_ws_policy - objold_ui_field = {0}".format(objold_ui_field))

        field_chef_value = node.attributes.get_dotted(field_chef)

        diff = len(obj_ui_field) - len(objold_ui_field)

        if diff == 0:
            self.log("debug","tasks.py ::: has_changed_ws_policy - obj/objold iguales")
            updated =  obj_ui_field != objold_ui_field
        elif diff > 0:
            self.log("debug","tasks.py ::: has_changed_ws_policy - obj > objold")
            updated = any(x not in field_chef_value for x in obj_ui_field)
        else:
            self.log("debug","tasks.py ::: has_changed_ws_policy - obj < objold")
            updated = any(x in field_chef_value for x in [y for y in objold_ui_field if y not in obj_ui_field])

        self.log("debug","tasks.py ::: has_changed_ws_policy - updated = {0}".format(updated))
        return updated


    def has_changed_user_policy(self, node, obj_ui, objold_ui, field_chef, priority_obj):
        '''
        This method checks whether the "field_chef" policy field changed for the current object.

        Args:
            node (ChefNode): reserved node in Chef, receiver the policy.

            field_chef (str): policy field path. Example: gecos_ws_mgmt.software_mgmt.package_res.package_list

            obj_ui (list): policy fields and their values for the policy parameter and current object
                           Example: {'launchers': [{'name':'evince','action':'add'},{'name':'xournal','action':'add'}]}

            objold_ui (list): policy fields and their values for the policy parameter and old object (before executed action)
                              Example: {'launchers': [{'name':'evince','action':'remove'},{'name':'xournal','action':'add'}]}

        Returns:
            bool:  True if policy field changed and its value not in stored value in Chef node. False otherwise.
        '''
        self.log("info","tasks.py ::: Starting has_changed_user_policy method ...")
        self.log("debug","tasks.py ::: has_changed_user_policy - obj_ui = {0}".format(obj_ui))
        self.log("debug","tasks.py ::: has_changed_user_policy - objold_ui = {0}".format(objold_ui))
        # Checking changes in object.
        if objold_ui is None:
            return True
        
        if obj_ui == objold_ui:
            return False

        # Checking changes in Chef node.
        field_chef_value = node.attributes.get_dotted(field_chef)
                                                                                                            
        self.log("debug","tasks.py ::: has_changed_user_policy - field_chef_value = {0}".format(field_chef_value))
        username = get_username_chef_format(priority_obj)
        self.log("debug","tasks.py ::: has_changed_user_policy -  username = {0}".format(username))
        updated = False

        for policy_type in obj_ui.keys():
            self.log("debug","tasks.py ::: has_changed_user_policy - policy_type = {0}".format(policy_type))
            if isinstance(field_chef_value.get(username,{}).get(policy_type), list) or field_chef_value.get(username,{}).get(policy_type) is None:
                if field_chef_value.get(username,{}).get(policy_type) is None:                   
                    updated = True
                elif obj_ui.get(policy_type) != []:
                    # Check if all the values in the policy are in Chef
                    for obj in obj_ui.get(policy_type):
                        if obj not in field_chef_value.get(username,{}).get(policy_type):
                            # There is a new value added in the policy
                            updated = True
                            break
                    
                    # Check if objold_ui contains this policy             
                    if not updated and not (policy_type in objold_ui.keys()):
                        # The policy has been added to the object
                        updated = True
                        break
                    
                    if not updated:
                        # Get the keys that exists in objold_ui[policy_type] but does not exists in obj_ui[policy_type]
                        keysdiff = [y for y in objold_ui[policy_type] if y not in obj_ui[policy_type]]
                        
                        # Check if any of the keys exists is in chef is updated
                        # (the user removed a value from the policy)
                        updated = any(x in field_chef_value.get(username,{}).get(policy_type) for x in keysdiff)
                        
        self.log("debug","tasks.py ::: has_changed_user_policy - updated = {0}".format(updated))                                                                                                
        return updated

    def has_changed_ws_emitter_policy(self, node, obj_ui, objold_ui, field_chef):
        '''
        Checks if the workstation emitter policy has changed or is equal to the policy stored in the node chef.
        This policy is emitter, that is that the policy contains related objects (printers and repositories)
        '''

        if obj_ui == objold_ui:
            return False

        field_chef_value = node.attributes.get_dotted(field_chef)

        if obj_ui.get('object_related_list', False):
            related_objs = obj_ui['object_related_list']
            for related_obj in related_objs:
                if obj_ui['type'] == 'repository':
                    if not any(d['repo_name'] == related_obj['name'] for d in field_chef_value):
                        return True

                elif not any(d['name'] == related_obj['name'] for d in field_chef_value):
                    return True
            return True
        related_objs = obj_ui
        for field_value in field_chef_value:
            if obj_ui['type'] == 'repository':
                field_chef = field_value['repo_name']
            else:
                field_chef = field_value['name']
            if related_objs['name'] == field_chef:
                for attribute in field_value.keys():
                    if attribute == 'repo_name':
                        if related_objs['name'] != field_value[attribute]:
                            return True
                    elif related_objs[attribute] != field_value[attribute]:
                        return True
        return False

    def has_changed_user_emitter_policy(self, node, obj_ui, objold_ui, field_chef, priority_obj):
        '''
        Checks if the user emitter policy has changed or is equal to the policy stored in the node chef.
        This policy is emitter, that is that the policy contains related objects (storage)
        '''
        self.log("debug","tasks.py ::: has_changed_user_emitter_policy - obj_ui = {0}".format(obj_ui))
        self.log("debug","tasks.py ::: has_changed_user_emitter_policy - objold_ui = {0}".format(objold_ui))
        if obj_ui == objold_ui:
            return False

        if objold_ui is None or objold_ui=={}:
            return True

        field_chef_value = node.attributes.get_dotted(field_chef)
        self.log("debug","tasks.py ::: has_changed_user_emitter_policy - priority_obj['name'] = {0}".format(priority_obj['name']))
        username = get_username_chef_format(priority_obj)
        self.log("debug","tasks.py ::: has_changed_user_emitter_policy - username = {0}".format(username))
        field_chef_value_storage = field_chef_value.get(username,{}).get('gtkbookmarks',[])
        self.log("debug","tasks.py ::: has_changed_user_emitter_policy - field_chef_value_storage = {0}".format(field_chef_value_storage))
        if obj_ui.get('object_related_list', False):
            related_objects = obj_ui['object_related_list']

            for obj in related_objects:
                # Find a new related object added for current obj
                if not any(d['name'] == obj['name'] for d in field_chef_value_storage):
                    return True

            # Find related objects that has been removed in current policy
            old_rel_objnames = [x['name'] for x in objold_ui.get('object_related_list',[])] # objold = {} when invokes apply_policies_to_%s (ou,group,user,computer)
            cur_rel_objnames = [y['name'] for y in obj_ui.get('object_related_list',[])]
            removed_objnames = [oldname for oldname in old_rel_objnames if oldname not in cur_rel_objnames]

            # True if related objects which have been removed are in chef node. It's necessary apply merge algorithm,
            # because they may not be there anymore.
            return any(x in [j['name'] for j in field_chef_value_storage] for x in removed_objnames)
            
        related_objects = obj_ui
        for field_value in field_chef_value_storage:
            if related_objects['name'] == field_value['name']:
                for attribute in field_value.keys():
                    if related_objects[attribute] != field_value[attribute]:
                        return True
        return False

    def update_ws_mergeable_policy(self, node, action, field_chef, field_ui, policy, update_by_path, obj_ui_field, objold_ui_field):
        '''
        This method updates the policy field on the chef node, with the resulting merge value of the policy for the current object.

        Args:
            node (ChefNode)        : reserved node in Chef, receiver the policy.
            action (str)           : Action ("created","changed") that Gecos administrator has performed on the current object ("ou","group","computer") 
            field_chef (str)       : policy field path. Example: gecos_ws_mgmt.software_mgmt.package_res.package_list
            field_ui (str|callable): When is a string type, name of the policy field (package_list). Otherwise (callable), a function.
            policy (dict)          : complete policy with all its fields. Example: 

              {  
                 u'slug':u'package_res',
                 u'name':u'Packages management',
                 u'name_es':u'Administracion de paquetes',
                 u'is_emitter_policy':False,
                 u'support_os':[  
                    u'GECOS V3',
                    u'GECOS V2',
                    u'Ubuntu 14.04.1 LTS',
                    u'GECOS V3 Lite',
                    u'Gecos V2 Lite'
                 ],
                 u'is_mergeable':True,
                 u'path':u'gecos_ws_mgmt.software_mgmt.package_res',
                 u'_id':ObjectId('593a8f050435643b8ba03630'),
                 u'targets':[  
                    u'ou',
                    u'computer',
                    u'group'
                 ],
                 u'schema':{  
                    u'title_es':u'Administracion de paquetes',
                    u'properties':{  
                       u'package_list':{  
                          u'title':u'Package list',
                          u'minItems':0,
                          u'items':{  
                             u'mergeIdField':[  
                                u'name'
                             ],
                             u'required':[  
                                u'name',
                                u'version',
                                u'action'
                             ],
                             u'order':[  
                                u'name',
                                u'version',
                                u'action'
                             ],
                             u'type':u'object',
                             u'properties':{  
                                u'action':{  
                                   u'title_es':u'Accion',
                                   u'enum':[  
                                      u'add',
                                      u'remove'
                                   ],
                                   u'type':u'string',
                                   u'title':u'Action'
                                },
                                u'version':{  
                                   u'title_es':u'Version',
                                   u'enum':[  

                                   ],
                                   u'type':u'string',
                                   u'autocomplete_url': 
                                   u'javascript:calculateVersions',
                                   u'title':u'Version'
                                },
                                u'name':{  
                                   u'title_es':u'Nombre',
                                   u'enum':[  

                                   ],
                                   u'type':u'string',
                                   u'autocomplete_url':u'/api/packages/',
                                   u'title':u'Name'
                                }
                             },
                             u'mergeActionField':u'action'
                          },
                          u'title_es':u'Lista de paquetes',
                          u'uniqueItems':True,
                          u'type':u'array'
                       }
                    },
                    u'type':u'object',
                    u'order':[  
                       u'package_list'
                    ],
                    u'title':u'Packages management'
                 }
              }
                            

            update_by_path (str)  : update_by policy field path. Example: gecos_ws_mgmt.software_mgmt.package_res.updated_by
            obj_ui_field (list)   : value of policy field in object after current executed action.
                                    Example: [{'name':'evince','version':'current','action':'add'},{'name':'xournal','version':'latest','action':'add'}]
            objold_ui_field (list): value of policy field in object before current executed action
                                    Example: [{'name':'evince','version':'current','action':'remove'},{'name':'xournal','version':'latest','action':'add'}])

        Returns:
            bool: True if the update was successful. False otherwise.
        '''
        self.log("info","tasks.py ::: Starting update_ws_mergeable_policy ...")
        if self.has_changed_ws_policy(node, obj_ui_field, objold_ui_field, field_chef) or action == DELETED_POLICY_ACTION:

            new_field_chef_value = []
           
            node_updated_by = node.attributes.get_dotted(update_by_path).items()
            self.log("debug","tasks.py ::: update_ws_mergeable_policy - node_updated_by = {0}".format(node_updated_by))
            nodes_ids = self.get_nodes_ids(node_updated_by)
            self.log("debug","tasks.py ::: update_ws_mergeable_policy - nodes_ids = {0}".format(nodes_ids))

            # Finding merge index fields
            mergeIdField, mergeActionField = self.search_mergefields(field_chef,field_ui,policy)

            # Obtaining objects from the mongo database ordered by proximity to the node, from the farthest to the nearest
            updater_nodes = self.order_items_by_priority(nodes_ids)

            for updater_node in updater_nodes:

                self.log("debug","tasks.py ::: update_ws_mergeable_policy - updater_node = {0}".format(updater_node['name']))
                try:
                    updater_node_ui = updater_node['policies'][text_type(policy['_id'])]
                except KeyError:
                    # Bugfix: updated_by contains mongo nodes in which the policy (policy_id) has been removed
                    # but this attribute was not updated correctly in chef. In this case, node_policy = {}
                    self.log("error","tasks.py ::: has_changed_ws_policy - Integrity violation: updated_by points attribute in chef node (id:{0}) to mongo node (id:{1}) without policy (id:{2})".format(node.name, updater_node['_id'],text_type(policy['_id'])))
                    continue

                if callable(field_ui): # encrypt_password
                    innode = field_ui(updater_node_ui, obj=updater_node, node=node, field_chef=field_chef)
                    self.log("debug","tasks.py ::: update_ws_mergeable_policy - innode = {0}".format(innode))
                else:
                    innode = updater_node_ui[field_ui]
                    self.log("debug","tasks.py ::: update_ws_mergeable_policy - innode = {0}".format(innode))

                if mergeIdField and mergeActionField: # NEW MERGE

                    try:
                        # At node: Removing opposites actions
                        nodupes_innode = self.group_by_multiple_keys(innode, mergeIdField, mergeActionField, True)
                        self.log("debug","tasks.py ::: update_ws_mergeable_policy - nodupes_innode = {0}".format(nodupes_innode))

                        # At hierarchy of nodes: Prioritizing the last action (closer to node)
                        new_field_chef_value += nodupes_innode
                        new_field_chef_value  = self.group_by_multiple_keys(new_field_chef_value, mergeIdField, mergeActionField, False)
                    except (AssertionError, TypeError) as _e:
                        # Do not merge. Invalid group_by_multiple_key args
                        self.log("debug","tasks.py ::: update_user_mergeable_policy - Invalid group_by_multiple_key args")
                        continue

                else: # OLD MERGE
                    new_field_chef_value += innode
                    
            self.log("debug","tasks.py ::: update_ws_mergeable_policy - new_field_chef_value = {0}".format(new_field_chef_value))
            try:
                node.attributes.set_dotted(field_chef,list(set(new_field_chef_value)))
            except TypeError:
                new_field_chef_value = self.remove_duplicated_dict(new_field_chef_value)
                node.attributes.set_dotted(field_chef, new_field_chef_value)
            return True
   
        return False


    def update_user_mergeable_policy(self, node, action, field_chef, field_ui, policy, priority_obj, priority_obj_ui, update_by_path, obj_ui, objold_ui):
        '''
        This method updates the policy field on the chef node, with the resulting merge value of the policy for the current object.

        Args:
            node (ChefNode)        : reserved node in Chef, receiver the policy.
            action (str)           : Action ("created","changed") that Gecos administrator has performed on the current object ("ou","group","computer")
            field_chef (str)       : policy field path. Example: gecos_ws_mgmt.software_mgmt.package_res.package_list
            field_ui (str|callable): When is a string type, name of the policy field (package_list). Otherwise (callable), a function.
            policy (dict)          : complete policy with all its fields.
            priority_obj           :  the highest priority object. In the case of user policies, the same user.
            priority_obj_ui        :  policy fields and their values for the policy parameter in priority_obj.
            update_by_path (str)   : update_by policy field path. Example: gecos_ws_mgmt.software_mgmt.package_res.updated_by
            obj_ui (dict)          : policy fields and their values for the policy parameter in current object
                                     Example: {'launchers': [{'name':'evince','version':'current','action':'add'},{'name':'xournal','version':'latest','action':'add'}]}
            objold_ui (dict)       : policy fields and their values for the policy parameter in old object (before executed action)
                                     Example: {'launchers': [{'name':'evince','version':'current','action':'remove'},{'name':'xournal','version':'latest','action':'add'}])}

        Returns:
            bool: True if the update was successful. False otherwise.
        '''
        self.log("debug","tasks.py ::: Starting update_user_mergeable_policy ...")
        if self.has_changed_user_policy(node, obj_ui, objold_ui, field_chef, priority_obj) or action == DELETED_POLICY_ACTION:

            self.log("debug","tasks.py ::: update_user_mergeable_policy - priority_obj = {0}".format(priority_obj))

            new_field_chef_value = {}

            node_updated_by = node.attributes.get_dotted(update_by_path).items()
            self.log("debug","tasks.py ::: update_user_mergeable_policy - node_updated_by = {0}".format(node_updated_by))
            nodes_ids = self.get_nodes_ids(node_updated_by)
            self.log("debug","tasks.py ::: update_user_mergeable_policy - nodes_ids = {0}".format(nodes_ids))

            # Obtaining objects from the mongo database ordered by proximity to the node, from the farthest to the nearest
            updater_nodes = self.order_items_by_priority(nodes_ids)

            for updater_node in updater_nodes:
                try:
                    node_policy = updater_node['policies'][text_type(policy['_id'])]
                except KeyError:
                    # Bugfix: updated_by contains mongo nodes in which the policy (policy_id) has been removed 
                    # but this attribute was not updated correctly in chef. In this case, node_policy = {}
                    self.log("error","tasks.py ::: has_changed_user_policy - Integrity violation: updated_by attribute in chef node (id:{0}) points to mongo node (id:{1}) without policy (id:{2})".format(node.name, updater_node['_id'],text_type(policy['_id'])))
                    continue

                for policy_field in node_policy.keys():
                    # Finding merge index fields
                    mergeIdField, mergeActionField = self.search_mergefields(field_chef,policy_field,policy)
                    
                    if mergeIdField and mergeActionField:
                        try:
                            innode = node_policy[policy_field]
                            self.log("debug","tasks.py ::: update_user_mergeable_policy - innode = {0}".format(innode))

                            # At node: Removing opposites actions
                            nodupes_innode = self.group_by_multiple_keys(innode, mergeIdField, mergeActionField, True)
                            self.log("debug","tasks.py ::: update_user_mergeable_policy - nodupes_innode = {0}".format(nodupes_innode))

                            # At hierarchy of nodes: Prioritizing the last action (closer to node)
                            if policy_field not in new_field_chef_value:
                                # Initializing 
                                new_field_chef_value[policy_field] = []
                           
                            # Accumulator
                            new_field_chef_value[policy_field] += nodupes_innode
                            new_field_chef_value[policy_field]  = self.group_by_multiple_keys(new_field_chef_value[policy_field], mergeIdField, mergeActionField, False)
                        except (AssertionError, TypeError) as _e:
                            # Do not merge. Invalid group_by_multiple_key args
                            self.log("debug","tasks.py ::: update_user_mergeable_policy - Invalid group_by_multiple_key args")
                            continue

                    else:                    
                        if policy_field not in new_field_chef_value:
                            new_field_chef_value[policy_field] = []
                        new_field_chef_value[policy_field] += node_policy[policy_field]

            self.log("debug","tasks.py ::: update_user_mergeable_policy - new_field_chef_value = {0}".format(new_field_chef_value))
            obj_ui_field = field_ui(priority_obj_ui, obj=priority_obj, node=node, field_chef=field_chef)
            self.log("debug","tasks.py ::: update_user_mergeable_policy - obj_ui_field = {0}".format(obj_ui_field))
            self.log("debug","tasks.py ::: update_user_mergeable_policy - priority_obj['name'] = {0}".format(priority_obj['name']))
            self.log("debug","tasks.py ::: update_user_mergeable_policy - action = {0}".format(action))
            username = get_username_chef_format(priority_obj)
            self.log("debug","tasks.py ::: update_user_mergeable_policy - username = {0}".format(username))

            if obj_ui_field.get(username):
                for policy_field in policy['schema']['properties'].keys():
                    if policy_field in obj_ui_field.get(username) and policy_field in new_field_chef_value:
                        obj_ui_field.get(username)[policy_field] = new_field_chef_value[policy_field]
            elif action == DELETED_POLICY_ACTION:  # update node
                pass
            else:
                return False

            self.log("debug","tasks.py ::: update_user_mergeable_policy - obj_ui_field = {0}".format(obj_ui_field))
            node.attributes.set_dotted(field_chef, obj_ui_field)
            return True

        return False

    def update_ws_emitter_policy(self, node, action, policy, obj_ui_field, field_chef, obj_ui, objold_ui, update_by_path):
        '''
        Update node chef with a mergeable workstation emitter policy
        This policy is emitter, that is that the policy contains related objects (printers and repositories)
        '''
        if self.has_changed_ws_emitter_policy(node, obj_ui, objold_ui, field_chef) or action == DELETED_POLICY_ACTION:
            node_updated_by = node.attributes.get_dotted(update_by_path).items()
            nodes_ids = self.get_nodes_ids(node_updated_by)

            related_objects = self.get_related_objects(nodes_ids, policy, obj_ui['type'])

            node.attributes.set_dotted(field_chef, related_objects)
            return True

        return False
        

    def update_user_emitter_policy(self, node, action, policy, obj_ui_field, field_chef, obj_ui, objold_ui, priority_obj, priority_obj_ui, field_ui, update_by_path):
        '''
        Update node chef with a mergeable user emitter policy
        This policy is emitter, that is that the policy contains related objects (storage)
        '''
        if self.has_changed_user_emitter_policy(node, obj_ui, objold_ui, field_chef, priority_obj) or action == DELETED_POLICY_ACTION:
            node_updated_by = node.attributes.get_dotted(update_by_path).items()
            nodes_ids = self.get_nodes_ids(node_updated_by)

            related_objects = self.get_related_objects(nodes_ids, policy, obj_ui['type'])
            current_objs = field_ui(priority_obj_ui, obj=priority_obj, node=node, field_chef=field_chef)

            for objs in related_objects:
                if objs not in current_objs.get(priority_obj['name'],{}).get('gtkbookmarks',[]):
                    current_objs.get(priority_obj['name'],{}).get('gtkbookmarks',[]).append(objs)
            node.attributes.set_dotted(field_chef, current_objs)
            return True

        return False

    # INI: NEW MERGE ALGORITHM METHODS #

    def group_by_multiple_keys(self, input_data, mergeIdField, mergeActionField, opposite=False):
        '''
        This method groups by key the values of a list of dictionaries and eliminates the duplicates 
        or those that are opposed.
        
        Args:
            input_data (list of dicts): list of dictionaries. 
                                        Example: [{'name':'evince','version':'current','action':'add'},{'name':'evince','version':'current','action':'remove'}]
            mergeIdField (list)       : fields to group together.
                                        Example: ['name','version']
                                        Example: ['user','group']
            mergeActionField (list)   : action field.
                                        Example: "action"
                                        Example: "actiontorun"
            opposite (bool)           : True to remove duplicates, False to select the last value

        Returns:
            res (list)                :  list of dictionaries without opposites
                                         Example: input_data = [{'name':'evince','version':'current','action':'add'},{'name':'evince','version':'current','action':'remove'}]
                                                  res        = [] if opposite param is True
                                                  res        = [{'name':'evince','version':'current','action':'remove'}] if opposite is False
        '''
        from itertools import groupby
        from operator import itemgetter

        # Checking input_data is a list of dictionaries
        assert isinstance(input_data, list)
        assert all(isinstance(x,dict) for x in input_data)

        self.log("debug","tasks.py ::: Starting group_by_multiple_key ...")
        self.log("debug","tasks.py ::: group_by_multiple_keys - input_data = {0}".format(input_data))

        keygetter = itemgetter(*mergeIdField)
        result = []
        for _key, grp in groupby(sorted(input_data, key = keygetter), keygetter):
            group = list(grp)
            actions_list = [g[mergeActionField] for g in group]
            latest = {mergeActionField: actions_list}
            if opposite:
                if len(latest[mergeActionField]) > 1:
                    continue
            latest.update(group.pop()) # input_data
            result.append(latest)

        self.log("debug","tasks.py ::: group_by_multiple_keys - result = {0}".format(result))
        self.log("debug","tasks.py ::: Ending group_by_multiple_keys ...")
        
        return result

    def cmpType(self, objtype):
        '''
        This comparator function returns order by type of object.

        Args:
            objtype (str): object type. Values: 'ou','group','user','computer'

        Returns:
            order (int)  : comparison order for the objects
        '''
        try:
            order = next(pos for pos, otype in enumerate(ORDER_BY_TYPE_ASC) if otype == objtype)
        except:
            order = objtype # alphabetical order

        return order

    def order_items_by_priority(self, ids):
        '''
        This method sorts objects by priority: 
            - Firstly, by type: ous, groups, computers, users
            - Sencondly, by depth: path length
            - Finally, by name: alphabetical order
                                                                                                      
        Args:
            ids (list)  : identifiers of objects

        Returns:
            items (list): ordered list of objects by priority
        '''
        items = [item for item in self.db.nodes.find({'_id': {'$in': ids}})]
        items.sort(key=lambda x: (self.cmpType(x['type']), x['path'].count(','), x['name']), reverse=False)
        return items
        
    def search_mergefields(self, field_chef, field_ui, policy):
        '''    
        This method search merge indexes (mergeIdField, mergeActionField) for "field_chef" policy field.
 
        Args:
            field_chef (str)       : policy field path. Example: gecos_ws_mgmt.software_mgmt.package_res.package_list
            field_ui (str|callable): When is a string type, name of the policy field (package_list). Otherwise (callable), a function.
            policy (dict)          : complete policy with all its fields.
                                              

        Returns:
            mergeIdField (list)    : field name(s) to merge
            mergeActionField (list): actions to merge: "add", "remove"
        '''    
    
        self.log("debug","tasks.py ::: Starting search_mergefields ...")
                                                                                                 
        mergeIdField = mergeActionField = None

        search_field = field_chef.split(".")[-1] if callable(field_ui) else field_ui

        self.log("debug","tasks.py ::: search_mergefields: search_field = {0}".format(search_field))

        field_ui_from_policy = nested_lookup(search_field, policy)
        self.log("debug","tasks.py ::: search_mergefields: field_ui_from_policy = {0}".format(field_ui_from_policy))

        if len(field_ui_from_policy) > 0:
            # nested_lookup return list and is already list
            field_ui_from_policy = field_ui_from_policy.pop()
            if isinstance(field_ui_from_policy, dict) and field_ui_from_policy.get('type') == 'array':
                mergeIdField = field_ui_from_policy['items'].get('mergeIdField', None)
                mergeActionField = field_ui_from_policy['items'].get('mergeActionField',None)
              
        if bool(mergeIdField) != bool(mergeActionField):
            raise Exception("JSON malformed: both merge fields are required.")

        self.log("debug","tasks.py ::: search_mergefields: mergeIdField = {0}".format(mergeIdField))
        self.log("debug","tasks.py ::: search_mergefields: mergeActionField = {0}".format(mergeActionField))
        self.log("debug","tasks.py ::: Ending search_mergefields ...")
          
        return [mergeIdField, mergeActionField]

    # END: NEW MERGE ALGORITHM METHODS #

    def update_node_from_rules(self, rules, user, computer, obj_ui, obj, objold, action, node, policy, rule_type, parent_id, job_ids_by_computer):
        '''
        This function update a node from rules.
        Rules are the different fields in a policy.
        We have different cases:
            1 - The field is None and action is different to remove
            2 - The field is None and action is remove
            3 - The policy is not mergeable
            4 - The policy is mergeable
        '''
        updated = updated_updated_by = False
        attributes_jobs_updated = []
        attributes_updated_by_updated = []
        is_mergeable = policy.get('is_mergeable', False)

        for field_chef, field_ui in rules.items():
            self.log("debug","tasks.py ::: update_node_from_rules - field_ui = {0}".format(field_ui))
            self.log("debug","tasks.py ::: update_node_from_rules - field_chef = {0}".format(field_chef))
            # Ignore a user policy in a computer not calculated by "get_computer_of_user" method
            if 'user' in computer:
                self.log("debug","tasks.py ::: update_node_from_rules - COMPUTER = {0} USER = {1}".format(computer['name'], computer['user']['name']))
            else:
                self.log("debug","tasks.py ::: update_node_from_rules - COMPUTER = {0} USER = {1}".format(computer['name'], 'None'))

            # Removing get_related_computers_of_computer and get_related_computers_of_group
            if is_user_policy(field_chef) and 'user' not in computer:
                continue

            # Ignore a non user policy in a computer calculated by "get_computer_of_user" method
            if (not is_user_policy(field_chef)) and ('user' in computer):
                continue

            job_attr = '.'.join(field_chef.split('.')[:3]) + '.job_ids'
            updated_by_attr = self.get_updated_by_fieldname(field_chef, policy, obj, computer)
            priority_obj_ui = obj_ui
            obj_ui_field = None
            if (rule_type == 'policies' or not policy.get('is_emitter_policy', False)) and updated_by_attr not in attributes_updated_by_updated:
                updated_updated_by = updated_updated_by or self.update_node_updated_by(node, field_chef, obj, action, updated_by_attr, attributes_updated_by_updated)
            priority_obj = self.priority_object(node, updated_by_attr, obj, action)
            self.log("debug","tasks:::update_node_from_rules -> priority_obj = {0}".format(priority_obj))
            self.log("debug","tasks:::update_node_from_rules -> obj = {0}".format(obj))
            self.log("debug","tasks:::update_node_from_rules -> objold = {0}".format(objold))

            if objold:
                objold_ui = self.get_object_ui(rule_type, objold, node, policy)
            else:
                objold = objold_ui = {}
            self.log("debug","tasks:::update_node_from_rules -> obj_ui = {0}".format(obj_ui))
            self.log("debug","tasks:::update_node_from_rules -> OBJOLD_UI = {0}".format(objold_ui))

            # objcur_ui_field: value of policy field for current object
            # objold_ui_field: value of policy field for old object (before executed action)
            # Both of them are used to checking if object changed in has_changed_ws_policy method
            # obj_ui_field can not be used for not always storing the value of the current object, 
            # but the priority, which will sometimes match the current or not.
            curobj_ui_field = objold_ui_field = {}

            if priority_obj != obj:
                if rule_type == 'save' and not is_mergeable:
                    # We are saving an emitter type that is nor mergeable and 
                    # priority_obj != obj, so we don't have to take any action
                    continue 
                    
                if rule_type == 'policies':
                    # Priority obj_ui only have meaning on non emitter types
                    priority_obj_ui = self.get_object_ui(rule_type, priority_obj, node, policy)
                    self.log("debug","tasks:::update_node_from_rules -> priority_obj_ui = {0}".format(priority_obj_ui))
                
                
            if priority_obj.get('_id', None) == obj.get('_id', None) or action == DELETED_POLICY_ACTION or is_mergeable:
                if callable(field_ui):
                    if is_user_policy(field_chef):
                        priority_obj = computer['user']

                    obj_ui_field = field_ui(priority_obj_ui, obj=priority_obj, node=node, field_chef=field_chef)
                    if objold and objold_ui:
                        objold_ui_field = field_ui(objold_ui, obj=objold, node=node, field_chef=field_chef)
                    self.log("debug","tasks:::update_node_from_rules -> objold_ui = {0}".format(objold_ui))

                    self.log("debug","tasks:::update_node_from_rules -> objold_ui_field = {0}".format(objold_ui_field))
                    
                    curobj_ui_field = field_ui(obj_ui, obj=obj, node=node, field_chef=field_chef)
                    self.log("debug","tasks:::update_node_from_rules -> curobj_ui_field = {0}".format(curobj_ui_field))

                else:
                    # Policy fields that are not sent in the form are populated with their defaults
                    obj_ui_field = priority_obj_ui.get(field_ui, node.default.get_dotted(field_chef))
                    curobj_ui_field = obj_ui.get(field_ui, node.default.get_dotted(field_chef))
                    objold_ui_field  = objold_ui.get(field_ui, node.default.get_dotted(field_chef))
                    self.log("debug","tasks:::update_node_from_rules -> obj_ui_field = {0}".format(obj_ui_field))
                    if field_ui not in obj_ui:
                        obj_ui[field_ui] = node.default.get_dotted(field_chef)
                        self.log("debug","tasks:::update_node_from_rules - obj_ui = {0}".format(obj_ui))

                                                                                                
                if not is_mergeable:

                    if not priority_obj and action == DELETED_POLICY_ACTION: # priority_obj = {}
                        self.log("debug","tasks.py ::: update_node_from_rules - not is_mergeable - DELETED_POLICY_ACTION")
                        try:
                            delete_dotted(node.attributes, field_chef)
                            updated = True
                        except KeyError:
                            pass
                    else:
                        try:
                            value_field_chef = node.attributes.get_dotted(field_chef)
                        except KeyError:
                            value_field_chef = None

                        if obj_ui_field != value_field_chef:
                            self.log("debug","tasks.py ::: update_node_from_rules - not is_mergeable - obj_ui_field != value_field_chef")
                            node.attributes.set_dotted(field_chef, obj_ui_field)
                            updated = True

                elif is_mergeable:
                    update_by_path = self.get_updated_by_fieldname(field_chef, policy, obj, computer)

                    self.log("debug","tasks.py ::: update_node_from_rules - is_mergeable - update_by_path = {0}".format(update_by_path))

                    if obj_ui.get('type', None) == 'storage':
                        is_policy_updated = self.update_user_emitter_policy(node, action, policy, obj_ui_field, field_chef, obj_ui, objold_ui, priority_obj, priority_obj_ui, field_ui, update_by_path)
                    elif obj_ui.get('type', None) in ['printer', 'repository']:
                        is_policy_updated = self.update_ws_emitter_policy(node, action, policy, obj_ui_field, field_chef, obj_ui, objold_ui, update_by_path)
                    elif not is_user_policy(field_chef):
                        is_policy_updated = self.update_ws_mergeable_policy(node, action, field_chef, field_ui, policy, update_by_path, curobj_ui_field, objold_ui_field)
                    elif is_user_policy(field_chef):
                        is_policy_updated = self.update_user_mergeable_policy(node, action, field_chef, field_ui, policy, priority_obj, priority_obj_ui, update_by_path, obj_ui, objold_ui)

                    if is_policy_updated:
                        updated = True
            self.log("debug","tasks.py ::: update_node_from_rules - updated = {0}".format(updated))
            if job_attr not in attributes_jobs_updated:
                if updated:
                    self.update_node_job_id(user, obj, action, computer, node, policy, job_attr, attributes_jobs_updated, parent_id, job_ids_by_computer)
        return (node, (updated or updated_updated_by))

    def get_first_exists_node(self, ids, obj, action):
        '''
        Get the first exising node from a ids list
        '''
        for mongo_id in ids:
            node = self.db.nodes.find_one({'_id': ObjectId(mongo_id)})
            if node:
                if action != DELETED_POLICY_ACTION or text_type(obj.get('_id')) != mongo_id:
                    return node
        return {}

    def get_updated_by_fieldname(self, field_chef, policy, obj, computer):
        '''
        Get the path of updated_by field
        '''
        updated_path = '.'.join(field_chef.split('.')[:3])
        if is_user_policy(field_chef):
            if obj['type'] != 'user':
                user = computer['user']
            else:
                user = obj
            updated_path += '.users.' + get_username_chef_format(user)
        updated_path += '.updated_by'
        return updated_path

    def priority_object(self, node, updated_by_fieldname, obj, action):
        '''
        Get the priority from an object
        '''
        if obj['type'] in ['computer', 'user'] and action != DELETED_POLICY_ACTION:
            return obj
        try:
            updated_by = node.attributes.get_dotted(updated_by_fieldname).to_dict()
        except KeyError:
            updated_by = {}
        if not updated_by:
            if action == DELETED_POLICY_ACTION:
                return {}
            else:
                return obj
        priority_object = {}

        if updated_by.get('computer', None):
            if action != DELETED_POLICY_ACTION or text_type(obj.get('_id')) != updated_by['computer']:
                priority_object = self.db.nodes.find_one({'_id': ObjectId(updated_by['computer'])})
        if not priority_object and updated_by.get('user', None):
            if action != DELETED_POLICY_ACTION or text_type(obj.get('_id')) != updated_by['user']:
                priority_object = self.db.nodes.find_one({'_id': ObjectId(updated_by['user'])})
        if not priority_object and updated_by.get('group', None):
            priority_object = self.get_first_exists_node(updated_by.get('group', None), obj, action)
        if not priority_object and updated_by.get('ou', None):
            priority_object = self.get_first_exists_node(updated_by.get('ou', None), obj, action)
        return priority_object

    def update_node_updated_by(self, node, field_chef, obj, action, attr, attributes_updated):
        '''
        Updates the updated_by field of a node
        '''
        updated = False
        try:
            updated_by = node.attributes.get_dotted(attr).to_dict()
        except KeyError:
            updated_by = {}
        obj_id = text_type(obj['_id'])
        obj_type = obj['type']
        if obj_type in ['computer', 'user']:
            if action == DELETED_POLICY_ACTION:
                if obj_type in updated_by:
                    del updated_by[obj_type]
            else:
                updated_by[obj_type] = obj_id
            updated = True
        else:  # Ous or groups
            updated_by_type = updated_by.get(obj_type, [])
            if action == DELETED_POLICY_ACTION:
                try:
                    updated_by_type.remove(obj_id)
                    updated = True
                except ValueError:
                    pass
            elif obj_id not in updated_by_type:
                updated = True
                if obj_type == 'ou':
                    updated_by_type.append(obj_id)
                    updated_by_type = order_ou_by_depth(self.db, updated_by_type)
                else:
                    updated_by_type.append(obj_id)
                    updated_by_type = order_groups_by_depth(self.db, updated_by_type)
                    
            if updated_by_type:
                updated_by[obj_type] = updated_by_type
            elif obj_type in updated_by:
                del updated_by[obj_type]
        if updated:
            if is_user_policy(attr):
                users_dict_path = '.'.join(attr.split('.')[:-2])
                try:
                    if not node.attributes.get_dotted(users_dict_path):
                        node.attributes.set_dotted(users_dict_path, {})
                except KeyError:
                    node.attributes.set_dotted(users_dict_path, {})
            node.attributes.set_dotted(attr, updated_by)
            attributes_updated.append(attr)
        return updated
        
    def update_node_job_id(self, user, obj, action, computer, node, policy, attr, attributes_updated, parent_id, job_ids_by_computer):
        '''
        Update the jobs field of a node
        '''
        if node.attributes.has_dotted(attr):
            job_ids = node.attributes.get_dotted(attr)
        else:
            job_ids = []
        job_storage = JobStorage(self.db.jobs, user)
        job_status = 'processing'
        computer_name = computer['name']
        if is_user_policy(policy.get('path', '')) and 'user' in computer:
            computer['user_and_name'] = '%s / %s' % (computer_name, computer['user']['name'])
        else:
            computer['user_and_name'] = None
        job_id = job_storage.create(obj=obj,
                                    op=action,
                                    status=job_status,
                                    computer=computer,
                                    policy=policy,
                                    parent=parent_id,
                                    administrator_username=user['username'])
        job_ids.append(text_type(job_id))
        job_ids_by_computer.append(job_id)
        attributes_updated.append(attr)
        node.attributes.set_dotted(attr, job_ids)

    def disassociate_object_from_group(self, obj):
        '''
        Disassociate object from a group
        '''
        groups = self.db.nodes.find({'type': 'group', 'members': obj['_id']})
        for g in groups:
            self.db.nodes.update({
                '_id': g['_id']
            }, {
                '$pull': {
                    'members': obj['_id']
                }
            }, multi=False)

    def get_policies(self, rule_type, action, obj, objold):
        '''
        Get the policies to apply and the policies to remove from an object
        '''
        policies_apply = [(policy_id, action) for policy_id in obj[rule_type].keys()]
        if not objold:
            return policies_apply
        policies_delete = set(objold[rule_type].keys()) - set(obj[rule_type].keys())
        policies_delete = [(policy_id, DELETED_POLICY_ACTION) for policy_id in policies_delete]
        return policies_apply + policies_delete
        
    def get_groups(self, obj, objold):
        """Method that get the groups to add and to delete from an object.

        Args:
            self (object): self pointer.
            obj (object): Node (computer or user) that received the change.
            objold (object): Value of the node (computer or user) before the change.

        Returns:
            set: Set that contains tuples of (group_id, action). Where action could be "add" or "delete".

        """
        if not objold:
            return []
            
        obj_memberof = set()
        if 'memberof' in obj:
            obj_memberof = set(obj['memberof'])
            
        objold_memberof = set()
        if 'memberof' in objold:
            objold_memberof = set(objold['memberof'])
            
        
        members_add = obj_memberof - objold_memberof
        members_add = [(group_id, 'add') for group_id in members_add]
        
        members_delete = objold_memberof - obj_memberof
        members_delete = [(group_id, 'delete') for group_id in members_delete]

        return members_add + members_delete        

    def get_members(self, obj, objold):
        """Method that get the members to add and to delete from a group.

        Args:
            self (object): self pointer.
            obj (object): Group node that received the change.
            objold (object): Value of the group node before the change.

        Returns:
            set: Set that contains tuples of (node_id, action). Where action could be "add" or "delete".

        """
        if not objold:
            return []
            
        obj_members = set()
        if 'members' in obj:
            obj_members = set(obj['members'])
            
        objold_members = set()
        if 'members' in objold:
            objold_members = set(objold['members'])
            
        
        members_add = obj_members - objold_members
        members_add = [(obj_id, 'add') for obj_id in members_add]
        
        members_delete = objold_members - obj_members
        members_delete = [(obj_id, 'delete') for obj_id in members_delete]

        return members_add + members_delete        
        
        
    def has_changed_user_data(self, obj, objold):
        if objold is None:
            return True
        
        if (obj['email'] != objold['email'] 
            or  obj['first_name'] != objold['first_name']
            or  obj['last_name'] != objold['last_name']):
            
            return True
     
        
        return False
        
    def update_node(self, user, computer, obj, objold, node, action, parent_id, job_ids_by_computer, force_update):
        '''
        This method update the node with changed or created actions.
        Have two different cases:
            1 - object type is ou, user, computer or group.
            2 - object type is emitter: printer, storage or repository
        '''
        updated = False
        if action not in ['changed', 'created', 'deleted', 'recalculate policies']:
            raise ValueError('The action should be changed, created, deleted or recalculate policies')
        
        # Refesh policies is similar to a computer/user creation or ou/group change
        if action == 'recalculate policies':
            action = 'created'
            if obj['type'] in ('ou', 'group'):
                action = 'changed'
        
        if obj['type'] in RESOURCES_RECEPTOR_TYPES:  # ou, user, comp, group
            # Update object data
            if obj['type'] == 'user':
                username = get_username_chef_format(obj)
                if self.has_changed_user_data(obj, objold):
                    self.log('debug', 'task.py:: update_node - Updating user data: {0}'.format(obj['name']))
                    # Update user data
                    if not node.normal.has_dotted('gecos_info'):
                        node.normal.set_dotted('gecos_info', {})

                    if not node.normal.has_dotted('gecos_info.users'):
                        node.normal.set_dotted('gecos_info.users', {})
                        
                    if not node.normal.has_dotted('gecos_info.users.%s'%(username)):
                        node.normal.set_dotted('gecos_info.users.%s'%(username), {})
                        
                    node.normal.set_dotted('gecos_info.users.%s.email'%(username), obj['email'])
                    node.normal.set_dotted('gecos_info.users.%s.firstName'%(username), obj['first_name'])
                    node.normal.set_dotted('gecos_info.users.%s.lastName'%(username), obj['last_name'])
    
                    updated = True
                    
                if ((action == 'deleted' or action == 'detached') 
                    and node.normal.has_dotted('gecos_info')
                    and node.normal.has_dotted('gecos_info.users.%s'%(username))):
                    self.log('debug', 'task.py:: update_node - Deleting user data: {0}'.format(obj['name']))
                    
                    del node.normal['gecos_info']['users'][username]
                    updated = True            
                    
            
            # Update policies
            self.log('debug', 'task.py:: update_node - force_update: {0} is_updating_policies: {1}'.format(force_update, self.is_updating_policies(obj, objold)))
            if force_update or self.is_updating_policies(obj, objold):
                rule_type = 'policies'
                self.log('debug', 'task.py:: update_node - policies: {0}'.format(self.get_policies(rule_type, action, obj, objold)))
                for policy_id, action in self.get_policies(rule_type, action, obj, objold):
                    policy = self.db.policies.find_one({"_id": ObjectId(policy_id)})
                    if action == DELETED_POLICY_ACTION:
                        rules, obj_ui = self.get_rules_and_object(rule_type, objold, node, policy)
                    else:
                        rules, obj_ui = self.get_rules_and_object(rule_type, obj, node, policy)
                    node, updated_policy = self.update_node_from_rules(rules, user, computer, obj_ui, obj, objold, action, node, policy, rule_type, parent_id, job_ids_by_computer)
                    if not updated and updated_policy:
                        updated = True
                        
            return (node, updated)
        elif obj['type'] in RESOURCES_EMITTERS_TYPES:  # printer, storage, repository
            rule_type = 'save'
            if force_update or self.is_updated_node(obj, objold):
                policy = self.db.policies.find_one({'slug': emiter_police_slug(obj['type'])})
                rules, obj_receptor = self.get_rules_and_object(rule_type, obj, node, policy)
                node, updated = self.update_node_from_rules(rules, user, computer, obj, obj_receptor, objold, action, node, policy, rule_type, parent_id, job_ids_by_computer)
            return (node, updated)

    def validate_data(self, node, cookbook, api, validator=None):
        '''
        Useful method, validate the DATABASES
        '''
        try:
            schema = cookbook['metadata']['attributes']['json_schema']['object']
            instance = to_deep_dict(node.attributes)
            if validator is None:
                validate(instance, schema)
                
            else:
                validator(schema).validate(instance)
                
        except ValidationError as e:
            # Bugfix: Validation error "required property"
            # example:
            # u'boot_lock_res' is a required property Failed validating
            if 'is a required property' in e.message:
                self.log('debug',"validation error: e.validator_value = {0}".format(e.validator_value))
                # e.path: deque
                for required_field in e.validator_value:
                    e.path.append(required_field)
                    self.log('debug',"validation error: path = {0}".format(e.path))

                    # Required fields initialization
                    attr_type = e.schema['properties'][required_field]['type']
                    if  attr_type == 'array':
                        initial_value = []
                    elif attr_type == 'object':
                        initial_value = {}
                    elif attr_type == 'string':
                        initial_value = ''
                    elif attr_type == 'number':
                        initial_value = 0

                    # Making required fields dictionary
                    # example: {u'gecos_ws_mgmt': {u'sotfware_mgmt': {u'package_res':{u'new_field':[]}}}}
                    required_dict = recursive_defaultdict()
                    setpath(required_dict, list(e.path), initial_value)
                    self.log('debug',"validation error: required_dict = {0}".format(required_dict))

                    # node.default: default chef attributes
                    defaults_dict = node.default.to_dict()

                    # merging defaults with new required fields
                    merge_dict = dict_merge(defaults_dict,required_dict)
                    self.log('debug',"validation error: merge_dict = {0}".format(merge_dict))

                    # setting new default attributes
                    setattr(node,'default',NodeAttributes(merge_dict))

                    # Saving node
                    save_node_and_free(node)

                    # reset variables next iteration
                    del required_dict, defaults_dict, merge_dict
                    e.path.pop()


    def report_error(self, exception, job_ids, computer, prefix=None):
        '''
        if an error is produced, save the error in the job
        '''
        message = 'No save in chef server.'
        if prefix:
            message = "%s %s" % (prefix, message)
        message = "%s %s" % (message, text_type(exception))
        self.log("error","tasks.py ::: report_error - message = {0}".format(message))
        self.log("error",traceback.format_exc())
        for job_id in job_ids:
            self.db.jobs.update(
                {'_id': job_id},
                {'$set': {'status': 'errors',
                          'message': message,
                          'last_update': datetime.datetime.utcnow()}})
        if not computer.get('error_last_saved', False):
            self.db.nodes.update({'_id': computer['_id']},
                                 {'$set': {'error_last_saved': True}})

    def report_node_not_linked(self, computer, user, obj, action):
        '''
        if the node is not linked, report node not linked error
        '''
        message = 'No save in chef server. The node is not linked, it is possible that this node was imported from AD or LDAP'
        self.report_generic_error(user, obj, action, message, computer, status='warnings')

    def report_node_busy(self, computer, user, obj, action):
        '''
        if the node is busy, report node busy error
        '''
        message = 'No save in chef server. The node is busy'
        self.report_generic_error(user, obj, action, message, computer)

    def report_unknown_error(self, exception, user, obj, action, computer=None):
        '''
        Report unknown error
        '''
        message = 'No save in chef server. %s' % text_type(exception)
        self.report_generic_error(user, obj, action, message, computer)

    def report_generic_error(self, user, obj, action, message, computer=None, status='errors'):
        '''
        Report generic error
        '''
        self.log("error","tasks.py ::: report_generic_error - message = {0}".format(message))
        self.log("error",traceback.format_exc())
        job_storage = JobStorage(self.db.jobs, user)
        job_status = status
        job = dict(obj=obj,
                   op=action,
                   status=job_status,
                   message=message,
                   administrator_username=user['username'])
        if computer:
            job['computer'] = computer
        job_storage.create(**job)

    def object_action(self, user, obj, objold=None, action=None, computers=None,
                      api=None, cookbook=None, calculate_inheritance=True,
                      validator=None):
        '''
        This method try to get the node to make changes in it.
        Theses changes are called actions and can be: changed, created, moved and deleted.
        if the node is free, the method can get the node, it reserves the node and runs the action, later the node is saved and released.
        '''
           
        settings = get_current_registry().settings                                                        
        api = api or get_chef_api(settings, user)
        cookbook = cookbook or get_cookbook(api,
                    settings.get('chef.cookbook_name'))
        computers = computers or self.get_related_computers(obj)
                                                                                          
        # MacroJob
        job_ids_by_order = []
        name = "%s %s" % (obj['type'], action)
        self.log("debug","obj_type_translate {0}".format(obj['type']))
        self.log("debug","action_translate {0}".format(action))
        name_es = self._(action) + " " + self._(obj['type'])
        macrojob_storage = JobStorage(self.db.jobs, user)
        macrojob_id = macrojob_storage.create(obj=obj,
                                    op=action,
                                    computer=None,
                                    status='processing',
                                    policy={'name':name,'name_es':name_es},
                                    administrator_username=user['username'])
        invalidate_jobs(self.request, user)
        are_new_jobs = False
        
        if computers is None or len(computers) == 0:
            self.log("debug","No computers related with {0} {1}".format(obj['name'], obj['type']))
            
        for computer in computers:
            try:
                self.log("debug","object_action {0}".format(computer['name']))
                job_ids_by_computer = []
                node_chef_id = computer.get('node_chef_id', None)
                node = reserve_node_or_raise(node_chef_id, api, 'gcc-tasks-%s-%s' % (obj['_id'], random.random()), 10)
                if not node.get(settings.get('chef.cookbook_name')):
                    raise NodeNotLinked("Node %s is not linked" % node_chef_id)
                error_last_saved = computer.get('error_last_saved', False)
                error_last_chef_client = computer.get('error_last_chef_client', False)
                force_update = error_last_saved or error_last_chef_client
                node, updated = self.update_node(user, computer, obj, objold, node, action, macrojob_id, job_ids_by_computer, force_update)
                if job_ids_by_computer:
                    job_ids_by_order += job_ids_by_computer
                if not updated:
                    save_node_and_free(node)
                    continue
                are_new_jobs = True
                self.validate_data(node, cookbook, api, validator=validator)
                save_node_and_free(node)
                if error_last_saved:
                    self.db.nodes.update({'_id': computer['_id']},
                                         {'$set': {'error_last_saved': False}})
            except NodeNotLinked as e:
                self.report_node_not_linked(computer, user, obj, action)
                are_new_jobs = True
                save_node_and_free(node, api, refresh=True)
            except NodeBusyException as e:
                self.report_node_busy(computer, user, obj, action)
                are_new_jobs = True
            except ValidationError as e:
                if not job_ids_by_computer:
                    self.report_unknown_error(e, user, obj, action, computer)
                self.report_error(e, job_ids_by_computer, computer, 'Validation error: ')
                save_node_and_free(node, api, refresh=True)
                are_new_jobs = True
            except Exception as e:
                if not job_ids_by_computer:
                    self.report_unknown_error(e, user, obj, action, computer)
                self.report_error(e, job_ids_by_computer, computer)
                try:
                    save_node_and_free(node, api, refresh=True)
                except:
                    pass
                are_new_jobs = True
        job_status = 'processing' if job_ids_by_order else 'finished'
        self.db.jobs.update_one({'_id': macrojob_id},
                            {'$set': {'status': job_status,
                                      'childs':  len(job_ids_by_order),
                                      'counter': len(job_ids_by_order),
                                      'message': self._("Pending: %d") % len(job_ids_by_order)}})

        if are_new_jobs or job_status == 'finished':
            invalidate_jobs(self.request, user)
            
        # Trace inheritance
        if not calculate_inheritance:
            return
        
        self.log("debug","object_action - type = {0} action = {1}".format(obj['type'], action))
        
        if obj['type'] in RESOURCES_RECEPTOR_TYPES:  # ou, user, comp, group
            if action != 'deleted':
                # Get an updated 'inheritance' field because this field may have been modified by a previous task in the queue
                # when the administrator adds several changes to the queue and then clic on "apply changes" button
                updated_obj = self.db.nodes.find_one({'_id': obj['_id']})
                if not updated_obj:
                    self.log("error","object_action - Node not found  %s (%s,%s)" %(str(obj['_id']), sys._getframe().f_code.co_filename, sys._getframe().f_lineno))
                    return False   
                    
                if 'inheritance' in updated_obj:
                    obj['inheritance'] = updated_obj['inheritance']
                
                
            if action == 'recalculate policies':
                # When recalculating policies only the node policies information must be updated
                recalculate_policies_for_computers(self.logger, self.db, obj, computers)
                
                # The inheritance field may have been updated
                updated_obj = self.db.nodes.find_one({'_id': obj['_id']})
                if not updated_obj:
                    self.log("error","object_action - Node not found  %s (%s,%s)" %(str(obj['_id']), sys._getframe().f_code.co_filename, sys._getframe().f_lineno))
                    return False   
                    
                if 'inheritance' in updated_obj:
                    obj['inheritance'] = updated_obj['inheritance']
                
            if action == 'created':
                # When creating or moving an object we must change the inheritance of the node
                # event when it has no policies applied
                move_in_inheritance_and_recalculate_policies(self.logger, self.db, obj, obj)
                
                # The inheritance field may have been updated
                updated_obj = self.db.nodes.find_one({'_id': obj['_id']})
                if not updated_obj:
                    self.log("error","object_action - Node not found  %s (%s,%s)" %(str(obj['_id']), sys._getframe().f_code.co_filename, sys._getframe().f_lineno))
                    return False   
                    
                if 'inheritance' in updated_obj:
                    obj['inheritance'] = updated_obj['inheritance']
                
                
            if action == 'deleted' and obj['type'] == 'group' and ('members' in obj):
                # When a group is deleted we must remove it from all its members
                self.log("debug","object_action - Deleting a group!")
                for object_id in obj['members']:
                    member = self.db.nodes.find_one({'_id': object_id})
                    if not member:
                        self.log("error","object_action - Node not found  %s (%s,%s)" %(str(object_id), sys._getframe().f_code.co_filename, sys._getframe().f_lineno))
                        return False  

                    if not 'inheritance' in member:
                        continue                        
                        
                    remove_group_from_inheritance_tree(self.logger, self.db, obj, member['inheritance'])
                    self.db.nodes.update({'_id': member['_id']}, {'$set':{'inheritance': member['inheritance']}})
                    recalculate_inherited_field(self.logger, self.db, str(object_id))
                    
            else:
            
                # Changing an object (by adding or removing groups)
                groups_changed = False
                for group_id, group_action in self.get_groups(obj, objold):
                    self.log("debug","object_action - changing groups: group ID = {0} action = {1}".format(group_id, group_action))
                    group = self.db.nodes.find_one({'_id': group_id})
                    if not group:
                        self.log("error","object_action - Group not found  %s (%s,%s)" %(str(group_id), sys._getframe().f_code.co_filename, sys._getframe().f_lineno))
                        continue            
                
                    if group_action == 'add':
                        group_added = add_group_to_inheritance_tree(self.logger, self.db, group, obj['inheritance'])
                        groups_changed = (groups_changed or group_added)
                        
                    if group_action == 'delete':
                        group_deleted = remove_group_from_inheritance_tree(self.logger, self.db, group, obj['inheritance'])
                        groups_changed = (groups_changed or group_deleted)
                        
                if groups_changed:
                    self.log("debug","object_action - groups changed!")
                    # Update node in mongo db
                    self.db.nodes.update_one({'_id': obj['_id']},
                        {'$set':{'inheritance': obj['inheritance']}})
                    
                    # Refresh all policies of the added groups in the inheritance field
                    for group_id, group_action in self.get_groups(obj, objold):
                        if group_action == 'add':
                            group = self.db.nodes.find_one({'_id': group_id})
                            if not group:
                                self.log("error","object_action - Group not found  %s (%s,%s)" %(str(group_id), sys._getframe().f_code.co_filename, sys._getframe().f_lineno))
                                continue            

                            for policy_id, policy_action in self.get_policies('policies', 'changed', group, None):
                                policy = self.db.policies.find_one({"_id": ObjectId(policy_id)})
                                recalculate_inheritance_for_node(self.logger, self.db, policy_action, group, policy, obj)

                    obj['inheritance'] = recalculate_inherited_field(self.logger, self.db, str(obj['_id']))
                                
                if obj['type'] == 'group' and len(self.get_members(obj, objold)) > 0:
                    # When we are changing the members of a group we must ignore the change in policies
                    # because in api/__init.py__  we are comparing the group_without_policies with the old group
                    self.log("debug","object_action - member of group changed!")
                    return
                
                
                # Changing an object (only if it has policies applied)
                rule_type = 'policies'        
                for policy_id, policy_action in self.get_policies(rule_type, action, obj, objold):
                    self.log("debug","object_action - changing: policy_id = {0} action = {1}".format(policy_id, policy_action))
                    policy = self.db.policies.find_one({"_id": ObjectId(policy_id)})
                    trace_inheritance(self.logger, self.db, policy_action, obj, policy)        
                

    def object_created(self, user, objnew, computers=None,
                       api=None, cookbook=None, calculate_inheritance=True,
                       validator=None):
        self.object_action(user, objnew, action='created', computers=computers,
                           api=api, cookbook=cookbook,
                           calculate_inheritance=calculate_inheritance,
                           validator=validator)

    def object_refresh_policies(self, user, objnew, computers=None):
        self.object_action(user, objnew, action='recalculate policies', computers=computers)

    def object_changed(self, user, objnew, objold, action, computers=None,
                       api=None, cookbook=None, calculate_inheritance=True,
                       validator=None):
        self.object_action(user, objnew, objold, action, computers=computers,
                           api=api, cookbook=cookbook,
                           calculate_inheritance=calculate_inheritance,
                           validator=validator)

    def object_deleted(self, user, obj, computers=None):
        obj_without_policies = deepcopy(obj)
        obj_without_policies['policies'] = {}
        obj_without_policies['inheritance'] = []
        object_changed = getattr(self, '%s_changed' % obj['type'])
        object_changed(user, obj_without_policies, obj, action='deleted', computers=computers)

    def object_moved(self, user, objnew, objold):
        settings = get_current_registry().settings
        api = get_chef_api(settings, user)
        try:
            func = globals()['apply_policies_to_%s' % objnew['type']]

            # Updates path to Chef node after copying & pasting (computer)
            if objnew['type'] == 'computer':
                # TODO: change these "reserve" and "release" node functions
                # when the #248 pull request gets approved. 
                node = reserve_node_or_raise(objnew['node_chef_id'], api,
                    'gcc-tasks-%s-%s' % (objnew['_id'], random.random()), 10)
                add_path_attrs_to_node(node, objnew['path'], self.db.nodes,
                                       False)
                save_node_and_free(node)
                

        except KeyError:
            self.log('error', "object_moved - 'apply_policies_to_%s' not implemented!"%(objnew['type']))
            raise NotImplementedError
        except setPathAttrsToNodeException:
            self.log('error', "object_moved - Exception adding gecos path info to chef node")
            raise setPathAttrsToNodeException

        func(self.db.nodes, objnew, user, api, initialize=True, use_celery=False, policies_collection=self.db.policies)

    def object_emiter_deleted(self, user, obj, computers=None):
        name = "%s deleted" % obj['type']
        name_es = self._("deleted") + " " + self._(obj['type'])
        macrojob_storage = JobStorage(self.db.jobs, user)
        macrojob_storage.create(obj=obj,
                                op='deleted',
                                computer=None,
                                status='finished',
                                policy={'name':name,'name_es':name_es},
                                childs=0,
                                counter=0,
                                message="Pending: 0",
                                administrator_username=user['username'])
        invalidate_jobs(self.request, user)
        
        obj_id = text_type(obj['_id'])
        policy_id = text_type(get_policy_emiter_id(self.db, obj))
        object_related_list = get_object_related_list(self.db, obj)
        for obj_related in object_related_list:
            obj_old_related = deepcopy(obj_related)
            object_related_list = obj_related['policies'][policy_id]['object_related_list']
            if obj_id in object_related_list:
                object_related_list.remove(obj_id)
                if object_related_list:
                    self.db.nodes.update_one({'_id': obj_related['_id']}, 
                        {'$set': {'policies.%s.object_related_list'% policy_id:
                                  object_related_list}})
                else:
                    self.db.nodes.update_one({'_id': obj_related['_id']},
                        {'$unset': {'policies.%s' % policy_id: ""}})
                    obj_related = self.db.nodes.find_one({'_id': obj_related['_id']})
                node_changed_function = getattr(self, '%s_changed' % obj_related['type'])
                node_changed_function(user, obj_related, obj_old_related)

    def log_action(self, log_action, resource_name, objnew):
        self.log('info', '{0} {1} {2}'.format(resource_name, log_action, objnew['_id']))

    def group_created(self, user, objnew, computers=None,
                      api=None, cookbook=None, calculate_inheritance=True,
                      validator=None):
        self.log_action('created BEGIN', 'Group', objnew)
        self.object_created(user, objnew, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('created END', 'Group', objnew)

    def group_changed(self, user, objnew, objold, action='changed',
                      computers=None, api=None, cookbook=None,
                      calculate_inheritance=True,
                      validator=None):
        self.log_action('changed BEGIN', 'Group', objnew)
        self.object_changed(user, objnew, objold, action, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('changed END', 'Group', objnew)

    def group_moved(self, user, objnew, objold):
        self.log_action('moved BEGIN', 'Group', objnew)
        self.object_moved(user, objnew, objold)
        self.log_action('moved END', 'Group', objnew)

    def group_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.log_action('deleted BEGIN', 'Group', obj)
        self.object_deleted(user, obj, computers=computers)
        self.log_action('deleted END', 'Group', obj)

    def user_created(self, user, objnew, computers=None,
                     api=None, cookbook=None, calculate_inheritance=True,
                     validator=None):
        self.log_action('created BEGIN', 'User', objnew)
        if calculate_inheritance:
            # If we are not calculating the inheritance information
            # probably is because this is some kind of automated task
            # and we don't want to update the computers of the user
            settings = get_current_registry().settings
            api = api or get_chef_api(settings, user)
            objnew = update_computers_of_user(self.db, objnew, api)
            self.db.nodes.update_one({'_id': objnew['_id']},
                                 {'$set': {
                                      'computers': objnew['computers'] }})

        self.object_created(user, objnew, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('created END', 'User', objnew)

    def user_changed(self, user, objnew, objold, action='changed',
                     computers=None, api=None, cookbook=None,
                     calculate_inheritance=True,
                     validator=None):
        self.log_action('changed BEGIN', 'User', objnew)
        self.object_changed(user, objnew, objold, action, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('changed END', 'User', objnew)

    def user_moved(self, user, objnew, objold):
        self.log_action('moved BEGIN', 'User', objnew)
        self.object_moved(user, objnew, objold)
        self.log_action('moved END', 'User', objnew)

    def user_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.log_action('deleted BEGIN', 'User', obj)
        if direct_deleted is False:
            self.disassociate_object_from_group(obj)
        self.object_deleted(user, obj, computers=computers)
        self.log_action('deleted END', 'User', obj)

    def computer_created(self, user, objnew, computers=None,
                         api=None, cookbook=None, calculate_inheritance=True,
                         validator=None):
        self.log_action('created BEGIN', 'Computer', objnew)
        self.object_created(user, objnew, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('created END', 'Computer', objnew)

    def computer_refresh_policies(self, user, obj, computers=None):
        # Refresh policies of a computer
        self.log_action('refresh_policies BEGIN', 'Computer', obj)
        settings = get_current_registry().settings

        self.log('debug', 'tasks.py ::: computer_refresh_policies - Recreate user-computer relashionship --------------')
        self.log('debug', 'tasks.py ::: computer_refresh_policies - obj={0}'.format(obj))
        # 1 - Disassociate computer from its users
        users = self.db.nodes.find({'type': 'user', 'computers': obj['_id']})
        for u in users:
            self.log('debug', 'tasks.py ::: computer_refresh_policies - remove computer from user: {0}'.format(u['name']))
            self.db.nodes.update({
                '_id': u['_id']
            }, {
                '$pull': {
                    'computers': obj['_id']
                }
            }, multi=False)
            
            
        # 2 - Associate computer to its users
        node_chef_id = obj.get('node_chef_id', None)
        gcc_sudoers  = set()
        if node_chef_id:
            api = get_chef_api(settings, user)
            node = reserve_node_or_raise(node_chef_id, api, 'gcc-tasks-%s-%s' % (obj['_id'], random.random()), 10)

            # Remove variables data
            self.log('debug', 'tasks.py ::: computer_refresh_policies - Removing variables data')
            if node.normal.has_dotted('gecos_info'):
                del node.normal['gecos_info']
 

            for u in node.attributes.get_dotted(USERS_OHAI):
                username = u['username']
                
                usr = self.db.nodes.find_one({'name': username, 'type': 'user', 'path': get_filter_in_domain(obj)})

                if not usr:
                    self.log('debug', 'tasks.py ::: computer_refresh_policies - Create user: {0}'.format(username))
                    user_model = User()
                    usr = user_model.serialize({'name': username,
                                                 'path': obj.get('path', ''),
                                                 'type': 'user',
                                                 'lock': obj.get('lock', ''),
                                                 'source': obj.get('source', '')})
    
                    usr = update_computers_of_user(self.db, usr, api)
        
                    del usr['_id']
                    usr_id = self.db.nodes.insert(usr)
                    usr = self.db.nodes.find_one({'_id': usr_id})
    
                else:
                    self.log('debug', 'tasks.py ::: computer_refresh_policies - Add computer to user: {0}'.format(username))
                    comptrs = usr.get('computers', [])
                    if obj['_id'] not in comptrs:
                        comptrs.append(obj['_id'])
                        self.db.nodes.update({'_id': usr['_id']}, {'$set': {'computers': comptrs}})
                        add_computer_to_user(obj['_id'], usr['_id'])
    
                # Sudoers
                if u['sudo']:
                    gcc_sudoers.add(username)
                    self.log("debug", "tasks.py ::: computer_refresh_policies - gcc_sudoers: {0}".format(gcc_sudoers))
                    
                else:
                    # Update node user data
                    usrname = get_username_chef_format(usr)
                    self.log('debug', 'tasks.py ::: computer_refresh_policies - Add info to gecos_info.users.{0}'.format(usrname))
                    if not node.normal.has_dotted('gecos_info'):
                        node.normal.set_dotted('gecos_info', {})
    
                    if not node.normal.has_dotted('gecos_info.users'):
                        node.normal.set_dotted('gecos_info.users', {})
                        
                    if not node.normal.has_dotted('gecos_info.users.%s'%(usrname)):
                        node.normal.set_dotted('gecos_info.users.%s'%(usrname), {})
                        
                    node.normal.set_dotted('gecos_info.users.%s.email'%(usrname), usr['email'])
                    node.normal.set_dotted('gecos_info.users.%s.firstName'%(usrname), usr['first_name'])
                    node.normal.set_dotted('gecos_info.users.%s.lastName'%(usrname), usr['last_name'])     
                
            # Set sudoers information
            self.log('debug', 'tasks.py ::: computer_refresh_policies - Update sudoers: {0}'.format(gcc_sudoers))
            self.db.nodes.update({'_id': obj['_id']}, {'$set': {'sudoers': list(gcc_sudoers)}})
            
            # Clean inheritance information
            self.db.nodes.update({'_id': obj['_id']}, { '$unset': { "inheritance": {'$exist': True } }})
    
            # Set processing jobs as finished
            self.log('debug', 'tasks.py ::: computer_refresh_policies - Set processing jobs as finished!')
            processing_jobs = self.db.jobs.find({"computerid": obj['_id'], 'status': 'processing'})
            for job in processing_jobs:
                macrojob = self.db.jobs.find_one({'_id': ObjectId(job['parent'])}) if 'parent' in job else None
                
                self.db.jobs.update({'_id': job['_id']},
                                    {'$set': {'status': 'finished',
                                              'last_update': datetime.datetime.utcnow()}})
                
                # Decrement number of children in parent
                if macrojob and 'counter' in macrojob:
                    macrojob['counter'] -= 1
                    self.db.jobs.update({'_id': macrojob['_id']},                                                                
                                        {'$set': {'counter': macrojob['counter'],
                                                  'message': self._("Pending: %d") % macrojob['counter'],
                                                  'status': 'finished' if macrojob['counter'] == 0 else macrojob['status']}})                
    
                    
                # 3 - Clean policies information
                ATTRIBUTES_WHITE_LIST = ['use_node', 'job_status', 'tags', 'gcc_link', 'run_list', 'gecos_info']
                for attr in node.normal:
                    if not attr in ATTRIBUTES_WHITE_LIST:
                        self.log('debug', 'tasks.py ::: computer_refresh_policies - Remove from Chef: {0}'.format(attr))
                        del node.normal[attr]
        
            save_node_and_free(node)
            
        # 4 - Recalculate policies of the computer
        if obj.get('policies', {}): 
            self.object_refresh_policies(user, obj, computers=None)
        
        refreshed_ous = []
        refreshed_groups = []
        
        computers = [obj]
        users = self.db.nodes.find({'type': 'user', 'computers': obj['_id']})
        for u in users:
            # Do not apply policies to sudoers
            if u['name'] in gcc_sudoers:
                self.log('debug', 'tasks.py ::: computer_refresh_policies - User {0} in sudoers'.format(u['name']))
                continue

            # Set user for the policies calculation      
            comp = deepcopy(obj)   
            comp['user'] = u    
            computers.append(comp)
            self.log('debug', 'tasks.py ::: computer_refresh_policies - User {0} NOT in sudoers'.format(u['name']))
        
        self.log('debug', 'tasks.py ::: computer_refresh_policies - Computers: {0}'.format(len(computers)))
        
        # 5 - Recalculate policies of the OUs
        ous = self.db.nodes.find(get_filter_ous_from_path(obj['path']))
        for ou in ous:
            if ou.get('policies', {}):
                self.log('debug', 'tasks.py ::: computer_refresh_policies - Recaculate policies for OU: {0}'.format(ou['name']))
                self.object_refresh_policies(user, ou, computers=computers)
                refreshed_ous.append(ou['_id'])
                
    
        # 6 - Recalculate policies of the Groups
        groups = self.db.nodes.find({'_id': {'$in': obj.get('memberof', [])}})
        for group in groups:
            if group.get('policies', {}):
                self.log('debug', 'tasks.py ::: computer_refresh_policies - Recaculate policies for group: {0}'.format(group['name']))
                self.object_refresh_policies(user, group, computers=computers)   
                refreshed_groups.append(group['_id'])
        
        # 7 - Recalculate policies of users
        users = self.db.nodes.find({'type': 'user', 'computers': obj['_id']})
        for u in users:
            # Do not apply policies to sudoers
            if u['name'] in gcc_sudoers:
                continue

            # Set user for the policies calculation         
            obj['user'] = u
            
            self.log('debug', 'tasks.py ::: computer_refresh_policies - Recaculate policies for user: {0}'.format(u['name']))
            # 7.1 - Recalculate policies of user OUs
            ous = self.db.nodes.find(get_filter_ous_from_path(u['path']))
            for ou in ous:
                if ou.get('policies', {}) and ou['_id'] not in refreshed_ous:
                    self.log('debug', 'tasks.py ::: computer_refresh_policies - Recaculate policies for OU: {0} in user: {1}'.format(ou['name'], u['name']))
                    self.object_refresh_policies(user, ou, computers=[obj])
                    refreshed_ous.append(ou['_id'])
        
            # 7.2 - Recalculate policies of user groups
            groups = self.db.nodes.find({'_id': {'$in': u.get('memberof', [])}})
            for group in groups:
                if group.get('policies', {}) and group['_id'] not in refreshed_groups:
                    self.log('debug', 'tasks.py ::: computer_refresh_policies - Recaculate policies for group: {0} in user: {1}'.format(group['name'], u['name']))
                    self.object_refresh_policies(user, group, computers=[obj])
                    refreshed_groups.append(group['_id'])
        
            # 7.3 - Recalculate policies of user
            if u.get('policies', {}):
                self.object_refresh_policies(user, u, computers=[obj])            
            
        
        self.log_action('refresh_policies END', 'Computer', obj)

    def computer_changed(self, user, objnew, objold, action='changed',
                         computers=None, api=None, cookbook=None,
                         calculate_inheritance=True,
                         validator=None):
        self.log_action('changed BEGIN', 'Computer', objnew)
        self.object_changed(user, objnew, objold, action, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('changed END', 'Computer', objnew)

    def computer_moved(self, user, objnew, objold):
        self.log_action('moved BEGIN', 'Computer', objnew)
        self.object_moved(user, objnew, objold)
        self.log_action('moved END', 'Computer', objnew)

    def computer_deleted(self, user, obj, computers=None, direct_deleted=True):
        # 1 - Delete computer from chef server
        settings = get_current_registry().settings
        self.log_action('deleted BEGIN', 'Computer', obj)
        self.object_deleted(user, obj, computers=computers)
        node_chef_id = obj.get('node_chef_id', None)
        if node_chef_id:
            api = get_chef_api(settings, user)
            node = Node(node_chef_id, api)
            node.delete()
            client = Client(node_chef_id, api=api)
            client.delete()
        if direct_deleted is False:
            # 2 - Disassociate computer from its users
            users = self.db.nodes.find({'type': 'user', 'computers': obj['_id']})
            for u in users:
                self.db.nodes.update({
                    '_id': u['_id']
                }, {
                    '$pull': {
                        'computers': obj['_id']
                    }
                }, multi=False)
            # 3 - Disassociate computers from its groups
            self.disassociate_object_from_group(obj)
        self.log_action('deleted END', 'Computer', obj)

    def ou_created(self, user, objnew, computers=None, api=None, cookbook=None,
                   calculate_inheritance=True,
                   validator=None):
        self.log_action('created BEGIN', 'OU', objnew)
        self.object_created(user, objnew, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('created END', 'OU', objnew)

    def ou_changed(self, user, objnew, objold, action='changed', computers=None,
                   api=None, cookbook=None, calculate_inheritance=True,
                   validator=None):
        self.log_action('changed BEGIN', 'OU', objnew)
        self.object_changed(user, objnew, objold, action, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('changed END', 'OU', objnew)

    def ou_moved(self, user, objnew, objold):
        self.log_action('moved BEGIN', 'OU', objnew)
        self.object_moved(user, objnew, objold)
        self.log_action('moved END', 'OU', objnew)

    def ou_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.log_action('deleted BEGIN', 'OU', obj)
        ou_path = '%s,%s' % (obj['path'], text_type(obj['_id']))
        types_to_remove = ('computer', 'user', 'group', 'printer', 'storage', 'repository', 'ou')
        for node_type in types_to_remove:
            nodes_by_type = self.db.nodes.find({'path': ou_path,
                                                'type': node_type})
            for node in nodes_by_type:
                node_deleted_function = getattr(self, '%s_deleted' % node_type)
                node_deleted_function(user, node, computers=computers, direct_deleted=False)
        self.db.nodes.remove({'path': ou_path})
        name = "%s deleted" % obj['type']
        name_es = self._("deleted") + " " + self._(obj['type'])
        macrojob_storage = JobStorage(self.db.jobs, user)
        macrojob_storage.create(obj=obj,
                                op='deleted',
                                computer=None,
                                status='finished',
                                policy={'name':name,'name_es':name_es},
                                childs=0,
                                counter=0,
                                message="Pending: 0",
                                administrator_username=user['username'])
        invalidate_jobs(self.request, user)
        self.log_action('deleted END', 'OU', obj)

    def printer_created(self, user, objnew, computers=None,
                        api=None, cookbook=None, calculate_inheritance=True,
                        validator=None):
        self.log_action('created BEGIN', 'Printer', objnew)
        self.object_created(user, objnew, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('created END', 'Printer', objnew)

    def printer_changed(self, user, objnew, objold, action='changed',
                        computers=None, api=None, cookbook=None,
                        calculate_inheritance=True,
                        validator=None):
        self.log_action('changed BEGIN', 'Printer', objnew)
        self.object_changed(user, objnew, objold, action, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('changed END', 'Printer', objnew)

    def printer_moved(self, user, objnew, objold):
        self.log_action('moved BEGIN', 'Printer', objnew)
        self.object_moved(user, objnew, objold)
        self.log_action('moved END', 'Printer', objnew)

    def printer_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.log_action('deleted BEGIN', 'Printer', obj)
        self.object_emiter_deleted(user, obj, computers=computers)
        self.log_action('deleted END', 'Printer', obj)

    def storage_created(self, user, objnew, computers=None,
                        api=None, cookbook=None, calculate_inheritance=True,
                        validator=None):
        self.log_action('created BEGIN', 'Storage', objnew)
        self.object_created(user, objnew, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('created END', 'Storage', objnew)

    def storage_changed(self, user, objnew, objold, action='changed',
                        computers=None, api=None, cookbook=None,
                        calculate_inheritance=True,
                        validator=None):
        self.log_action('changed BEGIN', 'Storage', objnew)
        self.object_changed(user, objnew, objold, action, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('changed END', 'Storage', objnew)

    def storage_moved(self, user, objnew, objold):
        self.log_action('moved BEGIN', 'Storage', objnew)
        self.object_moved(user, objnew, objold)
        self.log_action('moved END', 'Storage', objnew)

    def storage_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.log_action('deleted BEGIN', 'Storage', obj)
        self.object_emiter_deleted(user, obj, computers=computers)
        self.log_action('deleted END', 'Storage', obj)

    def repository_created(self, user, objnew, computers=None,
                           api=None, cookbook=None, calculate_inheritance=True,
                           validator=None):
        self.log_action('created BEGIN', 'Repository', objnew)
        self.object_created(user, objnew, computers=computers,
                            api=api, cookbook=cookbook,
                            validator=validator)
        self.log_action('created END', 'Repository', objnew)

    def repository_changed(self, user, objnew, objold, action='changed',
                           computers=None, api=None, cookbook=None,
                           calculate_inheritance=True,
                           validator=None):
        self.log_action('changed BEGIN', 'Repository', objnew)
        self.object_changed(user, objnew, objold, action, computers=computers,
                            api=api, cookbook=cookbook,
                            calculate_inheritance=calculate_inheritance,
                            validator=validator)
        self.log_action('changed END', 'Repository', objnew)

    def repository_moved(self, user, objnew, objold):
        self.log_action('moved BEGIN', 'Repository', objnew)
        self.object_moved(user, objnew, objold)
        self.log_action('moved END', 'Repository', objnew)

    def repository_deleted(self, user, obj, computers=None, direct_deleted=True):
        self.log_action('deleted BEGIN', 'Repository', obj)
        self.object_emiter_deleted(user, obj, computers=computers)
        self.log_action('deleted END', 'Repository', obj)


@task_prerun.connect
def init_jobid(sender, **kargs):
    """ Generate a new job id in every task run"""
    sender.init_jobid()


@task(base=ChefTask)
def task_test(value):
    self = task_test
    self.log('debug', text_type(self.db.adminusers.count()))
    return Ignore()


@task(base=ChefTask)
def object_created(user, objtype, obj, computers=None, api=None, cookbook=None,
                   calculate_inheritance=True,
                   validator=None):
    self = object_created

    func = getattr(self, '{0}_created'.format(objtype), None)
    if func is not None:
        try:
            return func(user, obj, computers=computers,
                        api=api, cookbook=cookbook,
                        calculate_inheritance=calculate_inheritance,
                        validator=validator)
        except Exception as e:
            self.report_unknown_error(e, user, obj, 'created')
            invalidate_jobs(self.request, user)
    else:
        self.log('error', 'The method {0}_created does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_refresh_policies(user, objtype, obj, computers=None):
    self = object_created

    func = getattr(self, '{0}_refresh_policies'.format(objtype), None)
    if func is not None:
        try:
            return func(user, obj, computers=computers)
        except Exception as e:
            self.report_unknown_error(e, user, obj, 'refresh_policies')
            invalidate_jobs(self.request, user)
    else:
        self.log('error', 'The method {0}_refresh_policies does not exist'.format(
            objtype))

@task(base=ChefTask)
def object_changed(user, objtype, objnew, objold, action='changed',
                   computers=None, api=None, cookbook=None,
                   calculate_inheritance=True,
                   validator=None):
    self = object_changed
    func = getattr(self, '{0}_changed'.format(objtype), None)
    if func is not None:
        try:
            return func(user, objnew, objold, action, computers=computers,
                        api=api, cookbook=cookbook,
                        calculate_inheritance=calculate_inheritance,
                        validator=validator)
        except Exception as e:
            self.report_unknown_error(e, user, objnew, 'changed')
            invalidate_jobs(self.request, user)
    else:
        self.log('error', 'The method {0}_changed does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_moved(user, objtype, objnew, objold):
    self = object_moved
    func = getattr(self, '{0}_moved'.format(objtype), None)
    if func is not None:
        try:
            return func(user, objnew, objold)
        except Exception as e:
            self.report_unknown_error(e, user, objnew, 'moved')
            invalidate_jobs(self.request, user)
    else:
        self.log('error', 'The method {0}_moved does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_deleted(user, objtype, obj, computers=None):
    self = object_deleted
    func = getattr(self, '{0}_deleted'.format(objtype), None)
    if func is not None:
        try:
            return func(user, obj, computers=computers)
        except Exception as e:
            self.report_unknown_error(e, user, obj, 'deleted')
            invalidate_jobs(self.request, user)
    else:
        self.log('error', 'The method {0}_deleted does not exist'.format(
            objtype))

@task(base=ChefTask)
def chef_status_sync(node_id, auth_user):
    self = chef_status_sync
    settings = get_current_registry().settings
    api = get_chef_api(settings, auth_user)   
    node = Node(node_id, api)    
    job_status = node.attributes.get('job_status')

    # After chef-client run, a report handler calls /api/chef_status
    # Previously, gcc_link attribute of chef node is updated by network policies
    gcc_link = node.attributes.get('gcc_link')
    self.log("info", "Saving gcc_link: {0}".format(gcc_link))
    self.db.nodes.update({'node_chef_id':node_id},{'$set': {'gcc_link':gcc_link}})

    # Update IP address
    ipaddress = node.attributes.get('ipaddress')
    self.log("info", "ipaddress: {0}".format(ipaddress))
    self.db.nodes.update({'node_chef_id':node_id},{'$set': {'ipaddress':ipaddress}})
        
    reserve_node = False
    if job_status:
        node = reserve_node_or_raise(node_id, api, 'gcc-chef-status-%s' % random.random(), attempts=3)
        reserve_node = True
        chef_client_error = False

        for job_id, job_status in job_status.to_dict().items():
            job = self.db.jobs.find_one({'_id': ObjectId(job_id)})
            if not job:
                continue
            # Parent
            macrojob = self.db.jobs.find_one({'_id': ObjectId(job['parent'])}) if 'parent' in job else None
            if job_status['status'] == 0:
                self.db.jobs.update({'_id': job['_id']},
                                    {'$set': {'status': 'finished',
                                              'last_update': datetime.datetime.utcnow()}})
                # Decrement number of children in parent
                if macrojob and 'counter' in macrojob:
                    macrojob['counter'] -= 1
            elif job_status['status'] == 2:
                self.db.jobs.update({'_id': job['_id']},
                                    {'$set': {'status': 'warnings',
                                              'message': job_status.get('message', 'Warning'),
                                              'last_update': datetime.datetime.utcnow()}})
                if macrojob:                                
                    macrojob['status'] = 'warnings'
            else:
                chef_client_error = True
                self.db.jobs.update({'_id': job['_id']},
                                    {'$set': {'status': 'errors',
                                              'message': job_status.get('message', 'Error'),
                                              'last_update': datetime.datetime.utcnow()}})
                if macrojob:                                
                    macrojob['status'] = 'errors'
            # Update parent                                 
            if macrojob:
                self.db.jobs.update({'_id': macrojob['_id']},                                                                
                                    {'$set': {'counter': macrojob['counter'],
                                              'message': self._("Pending: %d") % macrojob['counter'],
                                              'status': 'finished' if macrojob['counter'] == 0 else macrojob['status']}})
        self.db.nodes.update({'node_chef_id': node_id}, {'$set': {'error_last_chef_client': chef_client_error}})
        invalidate_jobs(self.request, auth_user)
        node.attributes.set_dotted('job_status', {})

    # Users identified by username
    computer = self.db.nodes.find_one({'node_chef_id': node_id, 'type':'computer'})
    if not computer:
        return {'ok': False,
                'message': 'This node does not exist (mongodb)'}

    self.log("debug","tasks.py ::: chef_status_sync - computer = {0}".format(computer))                 

    chef_node_usernames = set([d['username'] for d in node.attributes.get_dotted(USERS_OHAI)])
    gcc_node_usernames  = set([d['name'] for d in self.db.nodes.find({
                                'type':'user', 
                                'computers': {'$in': [computer['_id']]}
                         },
                         {'_id':0, 'name':1})
                     ])
    self.log("debug","tasks.py ::: chef_status_sync - chef_node_usernames = {0}".format(chef_node_usernames))
    self.log("debug","tasks.py ::: chef_status_sync - gcc_node_usernames = {0}".format(gcc_node_usernames))

    users_recalculate_policies = []
    reload_clients = False
    users_remove_policies = []

    # Bugfix invalidate_change
    self.request.user = auth_user
    self.request.GET = {}
    # Sudoers
    chef_sudoers = set([d['username'] for d in node.attributes.get_dotted(USERS_OHAI) if d['sudo']]) 
    gcc_sudoers  = set(computer.get('sudoers',[]))
    self.log("debug","tasks.py ::: chef_status_sync - chef_sudoers = {0}".format(chef_sudoers))
    self.log("debug","tasks.py ::: chef_status_sync - gcc_sudoers  = {0}".format(gcc_sudoers))

    # Users added/removed ?
    if set.symmetric_difference(chef_node_usernames, gcc_node_usernames): 
        self.log("info", "Must check users!")
        self.log("debug", "tasks.py ::: chef_status_sync - users added or removed = {0}".format(set.symmetric_difference(chef_node_usernames, gcc_node_usernames)))
        if not reserve_node:
            node = reserve_node_or_raise(node_id, api, 'gcc-chef-status-%s' % random.random(), attempts=3)

        
        # Add users or vinculate user to computer if already exists
        addusers = set.difference(chef_node_usernames, gcc_node_usernames)
        self.log("debug", "tasks.py ::: chef_status_sync - addusers = {0}".format(addusers))
        for add in addusers:
            user = self.db.nodes.find_one({'name': add, 'type': 'user', 'path': get_filter_in_domain(computer)})

            if not user:
                user_model = User()
                user = user_model.serialize({'name': add,
                                             'path': computer.get('path', ''),
                                             'type': 'user',
                                             'lock': computer.get('lock', ''),
                                             'source': computer.get('source', '')})

                user = update_computers_of_user(self.db, user, api)
    
                del user['_id']
                user_id = self.db.nodes.insert(user)
                user = self.db.nodes.find_one({'_id': user_id})
                reload_clients = True

            else:
                computers = user.get('computers', [])
                if computer['_id'] not in computers:
                    computers.append(computer['_id'])
                    self.db.nodes.update({'_id': user['_id']}, {'$set': {'computers': computers}})
                    add_computer_to_user(computer['_id'], user['_id'])
                    invalidate_change(self.request, auth_user)

            # Sudoers
            if add not in chef_sudoers:
                self.log("info", "tasks.py ::: chef_status_sync - Recalculate policies for user: {0}".format(user))
                users_recalculate_policies.append(user)
            else:
                gcc_sudoers.add(add)
                self.log("info", "tasks.py ::: chef_status_sync - gcc_sudoers: {0}".format(gcc_sudoers))
                
            # Update user data in chef node
            username = get_username_chef_format(user)
            if not node.normal.has_dotted('gecos_info'):
                node.normal.set_dotted('gecos_info', {})

            if not node.normal.has_dotted('gecos_info.users'):
                node.normal.set_dotted('gecos_info.users', {})
                
            if not node.normal.has_dotted('gecos_info.users.%s'%(username)):
                node.normal.set_dotted('gecos_info.users.%s'%(username), {})
                
            node.normal.set_dotted('gecos_info.users.%s.email'%(username), user['email'])
            node.normal.set_dotted('gecos_info.users.%s.firstName'%(username), user['first_name'])
            node.normal.set_dotted('gecos_info.users.%s.lastName'%(username), user['last_name'])
    
        # Removed users
        delusers = set.difference(gcc_node_usernames, chef_node_usernames)
        self.log("debug", "tasks.py ::: chef_status_sync - delusers = {0}".format(delusers))

        for delete in delusers:
            user = self.db.nodes.find_one({'name': delete,
                                           'type': 'user',
                                           'path': get_filter_in_domain(computer)})
            computers = user['computers'] if user else []
            if computer['_id'] in computers:
                users_remove_policies.append(deepcopy(user))
                computers.remove(computer['_id'])
                self.db.nodes.update({'_id': user['_id']}, {'$set': {'computers': computers}})
                invalidate_change(self.request, auth_user)
            
            username = get_username_chef_format(user)
            if (node.normal.has_dotted('gecos_info')
                and node.normal.has_dotted('gecos_info.users.%s'%(username))):
                del node.normal['gecos_info']['users'][username]

    else: # Sudoers (only rol changed)

        # normal-to-sudo
        normal_to_sudo = set.difference(chef_sudoers, gcc_sudoers)
        self.log("debug", "tasks.py ::: chef_status_sync - normal to sudo = {0}".format(normal_to_sudo))
        self.db.nodes.find({'name': {'$in': list(normal_to_sudo)}, 
                            'type': 'user',
                            'path': get_filter_in_domain(computer)})
        #users_remove_policies += list(sudo)
        #self.db.nodes.update({'_id': {'$in': [d['_id'] for d in sudo]}},{'$set': { 'inheritance':[],'policies':{}}}, multi=True)

        gcc_sudoers = gcc_sudoers.union(normal_to_sudo)
        self.log("debug", "tasks.py ::: chef_status_sync - normal-to-sudo - gcc_sudoers = {0}".format(gcc_sudoers))

        # sudo-to-normal
        sudo_to_normal = set.difference(gcc_sudoers, chef_sudoers)
        self.log("debug", "tasks.py ::: chef_status_sync - sudo to normal = {0}".format(sudo_to_normal))
        normal = self.db.nodes.find({'name': {'$in': list(sudo_to_normal)}, 
                                   'type': 'user',
                                   'path': get_filter_in_domain(computer)})
        users_recalculate_policies += list(normal)
        self.log("debug", "tasks.py ::: chef_status_sync - users_recalculate_policies = {0}".format(users_recalculate_policies))

        gcc_sudoers = gcc_sudoers.difference(sudo_to_normal)
        self.log("debug", "tasks.py ::: chef_status_sync - sudo-to-normal - gcc_sudoers = {0}".format(gcc_sudoers))

    # Upgrade sudoers
    self.db.nodes.update({'_id': computer['_id']}, {'$set': {'sudoers': list(gcc_sudoers)}})
    if reload_clients:
        update_tree(computer.get('path', ''))

    save_node_and_free(node)

    for user in users_recalculate_policies:
        apply_policies_to_user(self.db.nodes, user, auth_user)

    for user in users_remove_policies:
        remove_policies_of_computer(user, computer, auth_user)

    # Save node and free
    if job_status:
        save_node_and_free(node)

@task(base=ChefTask)
def script_runner(user, sequence, rollback=False):
    ''' Launches scripts from an update
    
    Args:
      user(object):         user doing update
      sequence(str):        sequence of update
      rollback(boolean):    True if rollback action. Otherwise, False
    '''
    self = script_runner
    settings = get_current_registry().settings
    self.log("info","tasks.py ::: script_runner - Starting ...")
    self.log("debug", "tasks.py ::: script_runner - user = {0}".format(user))
    self.log("debug", "tasks.py ::: script_runner - sequence = {0}".format(sequence))

    scriptdir = settings.get('updates.scripts').format(sequence)
    self.log("debug", "tasks.py ::: script_runner - scriptdir = {0}".format(scriptdir))


    if rollback:
        scripts = glob(scriptdir + "99-*")
        logname = settings.get('updates.rollback').format(sequence)
    else:
        # Exclude 99-rollback from automatic execution
        scripts = glob(scriptdir + "[0-8][0-9]*") + glob(scriptdir + "9[0-8]*")
        scripts.sort()
        logname = settings.get('updates.log').format(sequence)
        controlfile = settings.get('updates.control').format(sequence)
        shutil.copyfile(controlfile, logname)

    self.log("debug", "tasks.py ::: script_runner - scripts = {0}".format(scripts))
    self.log("debug", "tasks.py ::: script_runner - logname = {0}".format(logname))

    bufsize =0 
    logfile = open(logname,'a+', bufsize)

    env = os.environ.copy()
    env['CLI_REQUEST'] = 'True'
    env['UPDATE_DIR']  = settings.get('updates.dir') + sequence
    env['COOKBOOK_DIR']= settings.get('updates.cookbook').format(sequence)
    env['BACKUP_DIR']  = settings.get('updates.backups').format(sequence)
    env['CONFIG_URI']  = settings.get('config_uri')
    env['GECOS_USER']  = user.get('username', None)

    returncode = 0
    for script in scripts:
         
        header = 'SCRIPT %s' % os.path.basename(script)
        header = header.center(150,'*')
        logfile.write('\n\n ' + header + ' \n\n')
        self.log("debug", "tasks.py ::: script_runner - script = {0}".format(script))
        os.chmod(script, 0o755)

        env['SCRIPT_CODE'] = re.match('.*(\d{2})-.*', script).group(1)

        returncode = subprocess.call(script, shell=True, stdout=logfile, stderr=subprocess.STDOUT, env=env)

        if returncode != 0:
            self.log("error", "tasks.py ::: script_runner - returncode = {0}".format(returncode))
            break

    if not rollback:
        self.db.updates.update({'_id': sequence},{'$set':
            {'state': returncode, 'timestamp_end': int(time.time()) }})

    logfile.close()
