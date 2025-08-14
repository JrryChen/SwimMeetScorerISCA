import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'isca_swim_scorer.settings')
app = Celery('isca_swim_scorer')
app.config_from_object('django.conf:settings', namespace='CELERY')


@app.task
def debug_task():
    print('Hello, world!')
    return

app.autodiscover_tasks()