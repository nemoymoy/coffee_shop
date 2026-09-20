"""Celery configuration for Coffee Shop."""
from celery import Celery

app = Celery('coffee_shop')

# Читаем настройки Celery из настроек Django
app.config_from_object('django.conf:settings', namespace='CELERY')

# Указываем задачи для автообнаружения в приложениях
app.autodiscover_tasks(
    packages=['coffee_shop.apps.catalog', 'coffee_shop.apps.orders',
              'coffee_shop.apps.users', 'coffee_shop.apps.news'],
    related_name='tasks'
)

# Подключаем задачи из корневого модуля tasks.py через conf.imports
# (отложенный импорт — Django уже инициализирован к моменту запуска воркера)
app.conf.imports = ('coffee_shop.tasks',)


@app.task(bind=True, ignore_result=True)
def debug_task(self):
    """Тестовая задача для проверки Celery."""
    print(f'Request: {self.request!r}')
