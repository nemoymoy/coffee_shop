"""Celery configuration for Coffee Shop."""
import os
from celery import Celery

# Устанавливаем модуль настроек Django по умолчанию
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'coffee_shop.settings.dev')

app = Celery('coffee_shop')

# Читаем настройки Celery из настроек Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Автоматически находим задачи во всех приложениях
app.autodiscover_tasks()


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Тестовая задача для проверки Celery."""
    print(f'Request: {self.request!r}')
