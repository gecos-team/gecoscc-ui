from bson import ObjectId

from celery.task import Task, task
from celery.signals import task_prerun
from celery.exceptions import Ignore


class ChefTask(Task):
    abstract = True

    def __init__(self):
        self.db = self.app.conf.get('mongodb').get_database()
        self.init_jobid()
        self.logger = self.get_logger()

    def log(self, messagetype, message):
        assert messagetype in ('debug', 'info', 'warning', 'error', 'critical')
        op = getattr(self.logger, messagetype)
        op('[{0}] {1}'.format(self.jid, message))

    def init_jobid(self):
        if self.request is not None:
            self.jid = self.request.id
        else:
            self.jid = unicode(ObjectId())

    def get_related_computers_of_computer(self, obj, related_computers, related_objects):
        if related_objects is not None:
            if not obj in related_objects:
                related_objects.append(obj)
            else:
                return related_computers
        related_computers.append(obj)
        return related_computers

    def get_related_computers_of_group(self, obj, related_computers, related_objects):
        if not obj in related_objects:
            related_objects.append(obj)
        else:
            return related_computers
        for node_id in obj['members']:
            node = self.db.nodes.find_one({'_id': node_id})
            if not node in related_objects:
                self.get_related_computers(node, related_computers, related_objects)
        return related_computers

    def get_related_computers_of_ou(self, ou, related_computers, related_objects):
        if related_objects is not None:
            if not ou in related_objects:
                related_objects.append(ou)
            else:
                return related_computers
        computers = self.db.nodes.find({'path': {'$regex': '.*,%s.*' % ou['_id']},
                                        'type': 'computer'})
        for computer in computers:
            self.get_related_computers_of_computer(computer,
                                                   related_computers,
                                                   related_objects)
        return related_computers

    def get_related_computers(self, obj, related_computers=None, related_objects=None):
        if related_computers is None:
            related_computers = []
        if related_objects is None and obj['type'] == 'group':
            related_objects = []
        if obj['type'] == 'computer':
            return self.get_related_computers_of_computer(obj, related_computers, related_objects)
        elif obj['type'] == 'group':
            return self.get_related_computers_of_group(obj, related_computers, related_objects)
        elif obj['type'] in ('user', 'printer', 'storage'):
            ou_id = obj['path'].split(',')[-1]
            ou = self.db.nodes.find_one({'_id': ObjectId(ou_id)})
        elif obj['type'] == 'ou':
            ou = obj
        else:
            raise NotImplementedError
        return self.get_related_computers_of_ou(ou, related_computers, related_objects)

    def object_created(self, objnew):
        computers = self.get_related_computers(objnew)

    def object_changed(self, objnew, objold):
        computers = self.get_related_computers(objnew)

    def object_deleted(self, obj):
        computers = self.get_related_computers(obj)

    def log_action(self, log_action, resource_name, objnew):
        self.log('info', '{0} {1} {2}'.format(resource_name, log_action, objnew['_id']))

    def group_created(self, objnew):
        self.object_created(objnew)
        self.log_action('created', 'Group', objnew)

    def group_changed(self, objnew, objold):
        self.object_changed(objnew, objold)
        self.log_action('changed', 'Group', objnew)

    def group_deleted(self, obj):
        self.object_deleted(obj)
        self.log_action('deleted', 'Group', obj)

    def user_created(self, objnew):
        self.object_deleted(objnew)
        self.log_action('created', 'User', objnew)

    def user_changed(self, objnew, objold):
        self.object_changed(objnew, objold)
        self.log_action('changed', 'User', objnew)

    def user_deleted(self, obj):
        self.object_deleted(obj)
        self.log_action('deleted', 'User', obj)

    def computer_created(self, objnew):
        self.object_deleted(objnew)
        self.log_action('created', 'Computer', objnew)

    def computer_changed(self, objnew, objold):
        self.object_changed(objnew, objold)
        self.log_action('changed', 'Computer', objnew)

    def computer_deleted(self, obj):
        self.object_deleted(obj)
        self.log_action('deleted', 'Computer', obj)

    def ou_created(self, objnew):
        self.object_created(objnew)
        self.log_action('created', 'OU', objnew)

    def ou_changed(self, objnew, objold):
        self.object_changed(objnew, objold)
        self.log_action('changed', 'OU', objnew)

    def ou_deleted(self, obj):
        self.object_deleted(obj)
        self.log_action('deleted', 'OU', obj)

    def printer_created(self, objnew):
        self.object_created(objnew)
        self.log_action('created', 'Printer', objnew)

    def printer_changed(self, objnew, objold):
        self.object_changed(objnew, objold)
        self.log_action('changed', 'Printer', objnew)

    def printer_deleted(self, obj):
        self.object_deleted(obj)
        self.log_action('deleted', 'Printer', obj)

    def storage_created(self, objnew):
        self.object_created(objnew)
        self.log_action('created', 'Storage', objnew)

    def storage_changed(self, objnew, objold):
        self.object_changed(objnew, objold)
        self.log_action('changed', 'Storage', objnew)

    def storage_deleted(self, obj):
        self.object_deleted(obj)
        self.log_action('deleted', 'Storage', obj)


@task_prerun.connect
def init_jobid(sender, **kargs):
    """ Generate a new job id in every task run"""
    sender.init_jobid()


@task(base=ChefTask)
def task_test(value):
    self = task_test
    self.log('debug', unicode(self.db.adminusers.count()))
    return Ignore()


@task(base=ChefTask)
def object_created(objtype, obj):
    self = object_created

    func = getattr(self, '{0}_created'.format(objtype), None)
    if func is not None:
        return func(obj)

    else:
        self.log('error', 'The method {0}_created does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_changed(objtype, objnew, objold):
    self = object_changed
    func = getattr(self, '{0}_changed'.format(objtype), None)
    if func is not None:
        return func(objnew, objold)

    else:
        self.log('error', 'The method {0}_changed does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_deleted(objtype, obj):
    self = object_changed

    func = getattr(self, '{0}_deleted'.format(objtype), None)
    if func is not None:
        return func(obj)

    else:
        self.log('error', 'The method {0}_deleted does not exist'.format(
            objtype))
