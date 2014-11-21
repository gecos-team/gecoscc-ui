import time


def waiting_to_celery(db):
    print 'waiting to celery'
    current_jobs_count = db.jobs.count()
    print 'Current jobs: %s' % current_jobs_count
    time.sleep(10)
    current_jobs_count2 = db.jobs.count()
    if current_jobs_count2 > current_jobs_count:
        waiting_to_celery(db)