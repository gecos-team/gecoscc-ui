from pyramid.threadlocal import manager

from celery.task import Task, task


class ChefTask(Task):
    abstract = True
    pyramid = None
    db = None

    def __init__(self):
        self.pyramid = manager.stack[0]['request']
        self.db = self.pyramid.db


@task(base=ChefTask)
def task_test(value):
    self = task_test
    print self.pyramid.db.adminusers.count()
