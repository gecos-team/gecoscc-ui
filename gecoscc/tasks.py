from bson import ObjectId

from celery.task import Task, task

from celery.signals import task_prerun


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
        self.jid = unicode(ObjectId())

    def group_created(self, objnew):
        self.log('info', 'Group created {0}'.format(objnew['_id']))

    def group_changed(self, objnew, objold):
        self.log('info', 'Group changed {0}'.format(objnew['_id']))

    def group_deleted(self, obj):
        self.log('info', 'Group deleted {0}'.format(obj['_id']))

    def user_created(self, objnew):
        self.log('info', 'User created {0}'.format(objnew['_id']))

    def user_changed(self, objnew, objold):
        self.log('info', 'User changed {0}'.format(objnew['_id']))

    def user_deleted(self, obj):
        self.log('info', 'User deleted {0}'.format(obj['_id']))

    def ou_created(self, objnew):
        self.log('info', 'OU created {0}'.format(objnew['_id']))

    def ou_changed(self, objnew, objold):
        self.log('info', 'OU changed {0}'.format(objnew['_id']))

    def ou_deleted(self, obj):
        self.log('info', 'OU deleted {0}'.format(obj['_id']))


@task_prerun.connect
def init_jobid(sender, **kargs):
    """ Generate a new job id in every task run"""
    sender.init_jobid()


@task(base=ChefTask)
def task_test(value):
    self = task_test
    self.log('debug', unicode(self.pyramid.db.adminusers.count()))


@task(base=ChefTask)
def object_created(objtype, obj):
    self = object_created

    func = getattr(self, '{0}_created'.format(objtype), None)
    if func is not None:
        func(obj)

    else:
        self.log('error', 'The method {0}_created does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_changed(objtype, objnew, objold):
    self = object_changed

    func = getattr(self, '{0}_changed'.format(objtype), None)
    if func is not None:
        func(objnew, objold)

    else:
        self.log('error', 'The method {0}_changed does not exist'.format(
            objtype))


@task(base=ChefTask)
def object_deleted(objtype, obj):
    self = object_changed

    func = getattr(self, '{0}_deleted'.format(objtype), None)
    if func is not None:
        func(obj)

    else:
        self.log('error', 'The method {0}_deleted does not exist'.format(
            objtype))
