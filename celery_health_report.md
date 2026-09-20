# Отчёт о проверке работоспособности Celery

**Дата:** 2026-09-20  
**Проект:** Coffee Shop (Django 4.2.11 + Celery 5.3.6)  
**Статус:** ⚠️ **КРИТИЧЕСКАЯ ПРОБЛЕМА ОБНАРУЖЕНА**

---

## 1. Инфраструктура

| Компонент       | Статус | Детали |
|-----------------|--------|--------|
| **Redis (Broker)** | ✅ OK | `redis://redis:6379/0`, healthcheck passes |
| **PostgreSQL (DB)** | ✅ OK | PostgreSQL 15, healthcheck passes |
| **Celery Worker** | ⚠️ **Частично** | Запущен, подключён к Redis, но задачи не зарегистрированы |
| **Celery Beat** | ❓ Не запущен | Сервис `celery-worker` не включает beat-процесс |

### Конфигурация брокера и бэкенда

```
Broker:              redis://redis:6379/0
Result Backend:      django-db
Serializer:          json
Accept Content:      ['json']
Timezone:            Europe/Moscow
Concurrency:         solo (1 процесс)
Prefetch Count:      16
```

---

## 2. Зарегистрированные задачи

### Доступные задачи в коде (8 task-ов):

| # | Название задачи | Тип | Назначение |
|---|----------------|-----|------------|
| 1 | `send_order_confirmation_email` | `@shared_task` | Отправка email подтверждения заказа |
| 2 | `send_order_status_changed_email` | `@shared_task` | Уведомление об изменении статуса |
| 3 | `send_verification_email` | `@shared_task(bind=True, max_retries=3)` | Подтверждение email пользователя |
| 4 | `sync_yandex_delivery_status` | `@shared_task` | Синхронизация статусов Яндекс Доставки (Express + Other Day) |
| 5 | `accept_express_claims_pending` | `@shared_task` | Автоприём заявок Яндекс Express |
| 6 | `generate_daily_report` | `@shared_task` | Ежедневный отчёт (выручка, заказы, топ товары) |
| 7 | `update_promo_codes_expiry` | `@shared_task` | Деактивация истёкших промокодов (каждый час) |
| 8 | `release_expired_reservations` | `@shared_task` | Освобождение истёкших резервов товаров |
| — | `debug_task` | `@task(bind=True)` | Встроенная тестовая задача Celery |

---

## 3. Celery Beat Schedule (периодические задачи)

| Имя в расписании | Задача | Расписание |
|-------------------|--------|------------|
| `sync-yandex-delivery` | `coffee_shop.tasks.sync_yandex_delivery_status` | Каждые 5 минут |
| `accept-express-claims` | `coffee_shop.tasks.accept_express_claims_pending` | Каждые 2 минуты |
| `generate-daily-report` | `coffee_shop.tasks.generate_daily_report` | Ежедневно в 09:00 |
| `update-promo-codes` | `coffee_shop.tasks.update_promo_codes_expiry` | Каждый час (:00) |
| `release-expired-reservations` | `coffee_shop.tasks.release_expired_reservations` | Каждый час (:00) |

---

## 4. Результаты тестирования

### 4.1 Подключение и коммуникация

| Тест | Результат |
|------|-----------|
| Ping worker (`inspect ping`) | ✅ `celery@6d61acd4a4f4: OK` |
| Подключение к Redis | ✅ `Connected to redis://redis:6379/0` |
| Healthcheck Docker | ✅ `service healthy` |
| Статистика воркера (`inspect stats`) | ✅ PID=1, uptime=75524s, concurrency=solo |

### 4.2 Отправка задач в брокер

| Задача | Результат |
|--------|-----------|
| `generate_daily_report.delay()` | ✅ Task submitted (f4831615-...) |
| `update_promo_codes_expiry.delay()` | ✅ Task submitted (e45ab23d-...) |
| `release_expired_reservations.delay()` | ✅ Task submitted (3ae408ea-...) |
| `send_order_confirmation_email.delay(order_id)` | ✅ Task submitted (52e0f13b-...) |
| `sync_yandex_delivery_status.delay()` | ✅ Task submitted (cd07f2bd-...) |
| `accept_express_claims_pending.delay()` | ✅ Task submitted (8ca8e2e5-...) |

**Итого: 6/6 задач успешно отправлены в брокер Redis**

### 4.3 pytest — тесты задач

| Тест | Результат |
|------|-----------|
| `test_sync_no_matching_orders` | ✅ PASSED |
| `test_sync_orders_filtered_by_yandex_order_id` | ❌ FAILED |
| `test_sync_updates_status` | ❌ FAILED |
| `test_sync_delivered_status` | ❌ FAILED |
| `test_sync_service_error` | ❌ FAILED |

**Итого: 1/5 passed, 4/5 failed**

**Причина провалов:** Несоответствие между mock в тестах и реализацией в `tasks.py`:
- Тесты мокают `get_order_status`, но код задачи вызывает `get_request_info` / `get_express_claim_info`
- Это приводит к `FieldError` при сохранении Order — MagicMock подменяет значение поля

---

## 5. 🔴 КРИТИЧЕСКАЯ ПРОБЛЕМА: Задачи не регистрируются в Celery Worker

### Симптом

При запуске `celery inspect registered` воркер показывает пустой список задач:
```
->  celery@6d61acd4a4f4: OK
    - empty -
```

В логах воркера:
```
[tasks]
(empty)

[2026-09-20 20:11:46,624: ERROR/MainProcess] Received unregistered task of type
'coffee_shop.tasks.send_verification_email'. The message has been ignored and discarded.
```

### Причина

В проекте **два файла инициализации Celery**, создающих **два разных экземпляра** Celery app:

1. **`coffee_shop/__init__.py`** — импортируется первым (при импорте любого модуля пакета):
   ```python
   from celery import Celery
   app = Celery('coffee_shop')
   app.config_from_object('django.conf:settings', namespace='CELERY')
   app.autodiscover_tasks()  # ← без packages, ищет tasks.py в INSTALLED_APPS
   ```

2. **`coffee_shop/celery.py`** — содержит полную конфигурацию с задачами:
   ```python
   app = Celery('coffee_shop')
   app.autodiscover_tasks(
       packages=['coffee_shop.apps.catalog', ...],
       related_name='tasks'
   )
   import coffee_shop.tasks  # ← задачи импортируются здесь
   ```

**Проблема:** Воркер запускается через `celery -A coffee_shop worker`, что импортирует **только** `__init__.py`. Модуль `celery.py` никогда не импортируется, поэтому задачи `@shared_task` из `tasks.py` не регистрируются.

### Подтверждение

```python
# В Django shell:
from coffee_shop import app as init_app
from coffee_shop.celery import app as celery_app
# init_app is celery_app → False  (два разных экземпляра!)
```

### Решение

Необходимо привести к единой точке инициализации. Один из вариантов:

**Вариант A** — импортировать `celery.py` из `__init__.py`:
```python
# coffee_shop/__init__.py
from .celery import app  # noqa: F401
```
И удалить дублирующую инициализацию Celery из `__init__.py`.

**Вариант B** — перенести всю конфигурацию из `celery.py` в `__init__.py`.

**Вариант C** — изменить entrypoint воркера на `-A coffee_shop.celery worker`.

---

## 6. Дополнительные замечания

### 6.1 SecurityWarning
```
SecurityWarning: You're running the worker with superuser privileges (uid=0 euid=0)
```
Воркер запускается от root. Рекомендуется настроить `--uid` в Dockerfile.

### 6.2 DeprecationWarning
```
CPendingDeprecationWarning: The broker_connection_retry configuration setting
will no longer determine broker connection retry behavior in Celery 6.0
```
Требуется добавить `broker_connection_retry_on_startup = True` в настройки Celery.

### 6.3 Конфликт настроек
- `__init__.py` использует `coffee_shop.settings.base`
- `celery.py` использует `coffee_shop.settings.dev`
- Воркер в Docker использует `DJANGO_SETTINGS_MODULE=coffee_shop.settings.dev`

### 6.4 Result Backend
`django-db` бэкенд требует миграций `django_celery_results`. При вызове `celery call` из CLI возникает `AppRegistryNotReady` — Django не инициализирован при загрузке бэкенда.

---

## 7. Сводка

| Категория | Статус |
|-----------|--------|
| Redis Broker | ✅ Работает |
| PostgreSQL | ✅ Работает |
| Отправка задач в брокер | ✅ Работает (6/6) |
| Регистрация задач в воркере | ❌ **НЕ работает** |
| Выполнение задач воркером | ❌ **НЕ работает** (задачи игнорируются) |
| Celery Beat (расписание) | ❓ Не запущен |
| pytest тесты | ⚠️ 1/5 passed (баг в моках) |
| Конфигурация | ⚠️ Дублирование app, конфликт settings |

### Вывод

**Celery infrastructure настроен, но не функционален.** Задачи успешно отправляются в Redis-брокер, но воркер их не обрабатывает из-за отсутствия регистрации task-ов. Требуется исправление конфигурации инициализации Celery (см. §5).
