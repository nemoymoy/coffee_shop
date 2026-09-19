"""Celery configuration for Coffee Shop."""
import os
from celery import Celery

# Устанавливаем модуль настроек Django по умолчанию
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'coffee_shop.settings.dev')

app = Celery('coffee_shop')

# Читаем настройки Celery из настроек Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Указываем задачи для автообнаружения в приложениях
app.autodiscover_tasks(
    packages=['coffee_shop.apps.catalog', 'coffee_shop.apps.orders',
              'coffee_shop.apps.users', 'coffee_shop.apps.news'],
    related_name='tasks'
)

# Явно подключаем задачи из корневого модуля tasks.py
import coffee_shop.tasks  # noqa: F401


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Тестовая задача для проверки Celery."""
    print(f'Request: {self.request!r}')
