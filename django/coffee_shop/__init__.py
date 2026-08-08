import os

import django_celery_beat
import django_celery_results

# Celery app
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'coffee_shop.settings.base')

app = Celery('coffee_shop')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
