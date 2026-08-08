# Coffee Shop — Кофейня с доставкой и онлайн-заказами

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![Django 4.2](https://img.shields.io/badge/Django-4.2-092E20.svg)](https://djangoproject.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791.svg)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-Alpine-DC382D.svg)](https://redis.io)

---

## 📋 Содержание

- [Описание](#-описание)
- [Основные возможности](#-основные-возможности)
- [Технологический стек](#-технологический-стек)
- [Структура проекта](#-структура-проекта)
- [Требования](#-требования)
- [Установка и запуск](#-установка-и-запуск)
- [Переменные окружения](#-переменные-окружения)
- [API эндпоинты](#-api-эндпоинты)
- [Тестирование](#-тестирование)
- [Админ-панель](#-админ-панель)
- [Фоновые задачи](#-фоновые-задачи)
- [Безопасность](#-безопасность)
- [Бэкапы и восстановление](#-бэкапы-и-восстановление)
- [Мониторинг](#-мониторинг)

---

## 📝 Описание

**Coffee Shop** — полнофункциональный веб-сайт для кофейни с возможностью:
- Онлайн-каталога кофе и сопутствующих товаров
- Выбора параметров кофе (вес, помол, способ заваривания)
- Оформления заказов с доставкой (Яндекс Доставка) и самовывозом
- Платежей через ЮКасса (YooKassa)
- Личного кабинета с историей заказов
- Админ-панели для управления товарами, заказами, промокодами и пользователями

Проект развёртывается через Docker Compose и предназначен для production-использования на Ubuntu 22.04 LTS.

---

## ✨ Основные возможности

### 🛍 Для покупателей
- **Каталог** с фильтрами (категория, цена, сорт, обжарка, регион, SCA-рейтинг)
- **Карточка товара** с детальным описанием кофе (сорт, обжарка, регион, обработка, SCA score, tasting notes)
- **Выбор параметров кофе**:
  - Вес (кратный 50 г, от 50 до 1000 г)
  - Форма: в зёрнах или молотый
  - Способ заваривания (появляется только при заказе молотого кофе)
- **Корзина** с промокодами и автоматическим расчётом стоимости
- **Оформление заказа** с выбором доставки (самовывоз или Яндекс Доставка)
- **Оплата** через ЮКасса (онлайн) или наличными при получении
- **Личный кабинет** с историей заказов и статусами
- **Отзывы** на товары

### 🎨 Админ-панель
- Управление товарами, категориями, заказами, промокодами, отзывами
- Массовые операции (изменение статусов, экспорт в CSV)
- Визуальные бейджи для статусов и оценок SCA
- Предпросмотр изображений товаров
- Фильтры по статусу, категории, дате, наличию

### 🛠 Технические возможности
- **Адаптивный дизайн** (Bootstrap 5)
- **AJAX-корзина** без перезагрузки страницы
- **Интеграция с Яндекс Доставкой** (расчёт стоимости, создание заказов)
- **Платежи через ЮКасса** с webhook-обработкой
- **Email-уведомления** (SendGrid)
- **Фоновые задачи** через Celery + Redis
- **Rate limiting** на критичные эндпоинты
- **Structured JSON logging**

---

## 🛠 Технологический стек

| Компонент | Технология | Версия |
|-----------|-----------|--------|
| **Backend** | Django | 4.2 LTS |
| **Язык** | Python | 3.12 |
| **Frontend** | Bootstrap 5 | 5.3.2 |
| **БД** | PostgreSQL | 15 Alpine |
| **Кэш/Брокер** | Redis | Alpine |
| **Фоновые задачи** | Celery | 5.3+ |
| **API** | Django REST Framework | — |
| **Платежи** | ЮКасса (YooKassa) | API v2 |
| **Доставка** | Яндекс Доставка | OAuth 2.0 |
| **Email** | SendGrid | SMTP |
| **Web-сервер** | Nginx | Alpine |
| **SSL** | Let's Encrypt (Certbot) | — |
| **Контейнеризация** | Docker Compose | 3.8 |

---

## 📁 Структура проекта

```
coffee_shop/
├── docker-compose.yml              # Контейнеры: web, nginx, db, redis, celery-worker, certbot
├── .env.example                    # Шаблоны переменных окружения
├── .gitignore                      # Игнорируемые файлы
├── deploy.sh                       # Скрипт деплоя на сервер
├── backup.sh                       # Бэкап БД и медиафайлов
├── restore.sh                      # Восстановление из бэкапа
│
├── django/                         # Django-проект
│   ├── Dockerfile                  # Сборка контейнера web
│   ├── entrypoint.sh               # Стартовый скрипт контейнера
│   ├── manage.py                   # Утилита управления Django
│   ├── pytest.ini                  # Настройки pytest
│   ├── requirements/               # Зависимости Python
│   │   ├── base.txt               # Базовые пакеты
│   │   ├── dev.txt                # Dev-зависимости
│   │   └── prod.txt               # Production-зависимости
│   │
│   ├── coffee_shop/               # Главное приложение Django
│   │   ├── settings/              # Настройки (base, dev, prod, test)
│   │   ├── urls.py                # URL-маршрутизация
│   │   ├── views.py               # Общие view
│   │   ├── middleware.py          # Кастомные миддлвари
│   │   ├── celery.py              # Конфигурация Celery
│   │   ├── tasks.py               # Фоновые задачи
│   │   ├── context_processors.py  # Общие контекстные процессоры
│   │   ├── asgi.py / wsgi.py      # Точки входа ASGI/WSGI
│   │   │
│   │   ├── apps/                  # Приложения Django
│   │   │   ├── catalog/           # Каталог товаров
│   │   │   │   ├── models/        # Модели: Category, Product, Review
│   │   │   │   ├── services/      # Сервисы: Cart, Coffee, Pricing
│   │   │   │   ├── forms/         # Формы: CoffeeForm, ProductForm
│   │   │   │   ├── views.py       # View: каталог, товары
│   │   │   │   ├── urls.py        # URL каталога
│   │   │   │   └── admin.py       # Админ-категории и товары
│   │   │   │
│   │   │   ├── orders/            # Заказы
│   │   │   │   ├── models/        # Модели: Order, OrderItem, PromoCode
│   │   │   │   ├── services/      # Сервисы: Stock, Delivery, Payment, OAuth
│   │   │   │   ├── forms/         # Формы: CheckoutForm, OrderForm
│   │   │   │   ├── views.py       # View: корзина, оформление, webhook
│   │   │   │   ├── urls.py        # URL заказов
│   │   │   │   └── admin.py       # Админ-заказы и промокоды
│   │   │   │
│   │   │   ├── users/             # Пользователи
│   │   │   │   ├── views.py       # View: профиль, логин
│   │   │   │   ├── services.py    # Сервисы пользователей
│   │   │   │   └── admin.py       # Админ-пользователи
│   │   │   │
│   │   │   └── news/              # Новости и акции
│   │   │       ├── models/        # Модели: News, Promotion
│   │   │       ├── views.py       # View: новости, акции
│   │   │       └── admin.py       # Админ-новости
│   │   │
│   │   ├── templates/             # Шаблоны Django
│   │   │   ├── base.html          # Базовый шаблон
│   │   │   ├── home.html          # Главная
│   │   │   ├── catalog.html       # Каталог
│   │   │   ├── product_detail.html # Карточка товара
│   │   │   ├── cart.html          # Корзина
│   │   │   ├── checkout.html      # Оформление заказа
│   │   │   ├── order_success.html # Успешный заказ
│   │   │   ├── dashboard.html     # Личный кабинет
│   │   │   ├── profile.html       # Профиль
│   │   │   ├── news.html          # Новости
│   │   │   ├── about.html         # О кофейне
│   │   │   ├── emails/            # Email-шаблоны
│   │   │   └── ...
│   │   │
│   │   └── migrations/            # Миграции БД
│   │
│   ├── tests/                     # Тесты
│   │   ├── conftest.py            # Конфигурация pytest
│   │   ├── models/                # Тесты моделей
│   │   ├── services/              # Тесты сервисов
│   │   ├── views/                 # Тесты view
│   │   ├── api/                   # Тесты API
│   │   ├── forms/                 # Тесты форм
│   │   └── fixtures/              # Тестовые данные (YAML)
│   │
│   ├── static/                    # Статика
│   │   ├── css/                   # CSS-файлы
│   │   │   ├── coffee_theme.css   # Кофейная тема
│   │   │   └── components.css     # Кастомные компоненты
│   │   └── js/                    # JavaScript
│   │       ├── base.js            # Общие утилиты
│   │       ├── cart.js            # AJAX корзина
│   │       ├── coffee_selector.js # Выбор параметров кофе
│   │       └── checkout.js        # Валидация чекаута
│   │
│   └── media/                     # Загружаемые файлы (изображения)
│
├── nginx/                         # Конфигурация Nginx
│   ├── nginx.conf                 # Основной конфиг
│   └── sites-available/
│       └── coffee.conf            # Серверный блок
│
├── certbot/                       # SSL-сертификаты Let's Encrypt
│   └── www/                       # Webroot для Certbot
│
└── requirements/                  # Зависимости Python
    ├── base.txt                   # Базовые пакеты
    ├── dev.txt                    # Dev-зависимости
    └── prod.txt                   # Production-зависимости
```

---

## 📋 Требования

### Для локальной разработки:
- Python 3.12+
- Docker и Docker Compose
- PostgreSQL 15+ (или Docker-контейнер)
- Redis (или Docker-контейнер)

### Для production-развёртывания:
- Ubuntu 22.04 LTS
- Docker 20.10+ и Docker Compose v2
- Доменное имя, указывающее на сервер (например, `coffee-shop.example.com`)
- SSL-сертификат (Let's Encrypt)

---

## 🚀 Установка и запуск

### Локальный запуск (Development)

#### Шаг 1: Клонирование репозитория
```bash
git clone https://github.com/your-username/coffee_shop.git
cd coffee_shop
```

#### Шаг 2: Настройка переменных окружения
```bash
cp .env.example .env
# Отредактируйте .env и укажите нужные значения
```

#### Шаг 3: Запуск через Docker Compose
```bash
# Сборка и запуск всех сервисов
docker compose up -d --build

# Применение миграций
docker compose exec web python manage.py migrate

# Создание суперпользователя
docker compose exec web python manage.py createsuperuser

# Сборка статических файлов
docker compose exec web python manage.py collectstatic --noinput
```

#### Шаг 4: Проверка работы
- **Главная страница**: http://localhost:8000
- **Админ-панель**: http://localhost:8000/admin/
- **API Healthcheck**: http://localhost:8000/health/

---

## 🔧 Переменные окружения

Все переменные окружения находятся в файле `.env.example`. Вот основные из них:

### Основные настройки
```
# Django
SECRET_KEY=your-super-secret-key-at-least-50-chars-long
DEBUG=True/False
DOMAIN=yourdomain.com
ALLOWED_HOSTS=localhost,127.0.0.1,example.com

# Database
DATABASE_URL=postgresql://user:password@db:5432/coffee_shop
POSTGRES_DB=coffee_shop
POSTGRES_USER=coffee_shop
POSTGRES_PASSWORD=your-secure-password

# Redis
REDIS_URL=redis://redis:6379/0

# Email (SendGrid)
SENDGRID_USERNAME=apikey
SENDGRID_PASSWORD=your-sendgrid-api-key
EMAIL_FROM=noreply@yourdomain.com

# YooKassa (ЮКасса)
YOOKASSA_MERCHANT_ID=your-shop-id
YOOKASSA_API_KEY=your-secret-key
YOOKASSA_WEBHOOK_SECRET=your-webhook-secret
YOOKASSA_RETURN_URL=https://yourdomain.com/pay/callback/
YOOKASSA_TEST_MODE=true

# Yandex Delivery
YANDEX_DELIVERY_CLIENT_ID=your-client-id
YANDEX_DELIVERY_CLIENT_SECRET=your-client-secret
YANDEX_REDIRECT_URI=https://yourdomain.com/delivery/callback/
YANDEX_FROM_CITY=moscow

# Yandex Metrika
YANDEX_METRIKA_ID=your-metrika-id
YANDEX_METRIKA_WEBVIEWER=0
```

⚠️ **Важно:** Никогда не коммитьте файл `.env` в репозиторий!

---

## 🌐 API эндпоинты

### Основные страницы
| Эндпоинт | Описание |
|----------|----------|
| `/` | Главная страница |
| `/catalog/` | Каталог товаров |
| `/catalog/<slug>/` | Карточка товара |
| `/about/` | О кофейне |
| `/news/` | Список новостей |
| `/news/<slug>/` | Детальная страница новости |
| `/news/promotions/` | Список акций |

### Корзина и заказы
| Эндпоинт | Описание |
|----------|----------|
| `/cart/` | Корзина |
| `/cart/add/` (POST) | Добавить товар в корзину |
| `/checkout/` | Оформление заказа |
| `/checkout/success/<order_id>/` | Страница успешного заказа |

### Пользователи
| Эндпоинт | Описание |
|----------|----------|
| `/accounts/login/` | Авторизация |
| `/accounts/logout/` | Выход |
| `/dashboard/` | Личный кабинет |
| `/profile/` | Редактирование профиля |

### API и интеграции
| Эндпоинт | Описание |
|----------|----------|
| `/health/` | Healthcheck (мониторинг) |
| `/pay/webhook/` | ЮКасса webhook |
| `/delivery/callback/` | Яндекс Доставка callback |
| `/admin/` | Админ-панель |

### REST API
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/v1/products/` | Список товаров |
| GET | `/api/v1/products/<id>/` | Детали товара |
| POST | `/api/v1/cart/add/` | Добавить в корзину |
| POST | `/api/v1/orders/create/` | Создать заказ |

---

## 🧪 Тестирование

### Запуск тестов
```bash
# Перейти в директорию Django
cd django

# Запустить все тесты
pytest

# Запустить тесты с покрытием
pytest --cov=. --cov-report=html

# Запустить тесты для конкретного модуля
pytest tests/models/
pytest tests/services/
pytest tests/views/
```

### Структура тестов
```
tests/
├── conftest.py                          # Конфигурация pytest
├── fixtures/                            # Тестовые данные
│   ├── test_products.yaml
│   └── test_orders.yaml
├── models/                              # Тесты моделей
│   ├── test_category.py
│   ├── test_product.py
│   ├── test_order.py
│   ├── test_order_item.py
│   ├── test_promo_code.py
│   └── test_review.py
├── services/                            # Тесты сервисов
│   ├── test_cart_service.py
│   ├── test_coffee_service.py
│   ├── test_delivery_service.py
│   ├── test_pricing.py
│   └── test_stock_service.py
├── views/                               # Тесты view
│   ├── test_catalog.py
│   └── test_checkout.py
├── api/                                 # Тесты API
│   ├── test_yandex_delivery_api.py
│   └── test_payment_gateway.py
└── forms/                               # Тесты форм
    └── test_order_forms.py
```

### Ключевые сценарии тестирования
- Валидация веса (кратность 50 г)
- brewing_method при coffee_form=ground
- Контроль остатков
- Расчёт цены
- Моки Яндекс Доставки
- Промокоды (срок действия, лимиты)
- Конкурентные заказы

---

## 🎨 Админ-панель

Админ-панель доступна по адресу `/admin/`.

### Возможности админ-панели

#### Управление товарами (catalog)
- ✅ Кастомный changelist с фильтрами
- ✅ Предпросмотр изображений (image_thumbnail)
- ✅ Статусные бейджи для SCA (sca_score_badge)
- ✅ Цветовая индикация остатков (stock_color)
- ✅ Экспорт в CSV
- ✅ Массовые операции (make_available, unmake_available)
- ✅ Recalculate stock

#### Управление заказами (orders)
- ✅ Status badges с цветовой кодировкой
- ✅ Inline-редактирование OrderItem
- ✅ Массовое изменение статусов (mark_in_progress, mark_ready, mark_delivered, mark_cancelled)
- ✅ Экспорт заказов в CSV
- ✅ Предпросмотр информации о доставке
- ✅ Управление промокодами

#### Управление пользователями (users)
- ✅ Редактирование профилей
- ✅ Управление правами доступа

#### Управление категориями (catalog)
- ✅ Вложенные категории
- ✅ Фильтры по активности
- ✅ Предпросмотр товаров

#### Управление отзывами (catalog)
- ✅ Модерация отзывов (approve/unapprove)
- ✅ Фильтры по рейтингу

---

## ⚙️ Фоновые задачи

### Celery + Redis

Фоновые задачи выполняются через Celery с использованием Redis как брокера.

#### Список задач

| Задача | Описание | Периодичность |
|--------|----------|---------------|
| `send_order_confirmation_email` | Отправка email подтверждения заказа | При создании заказа |
| `send_order_status_changed_email` | Отправка уведомления об изменении статуса | При изменении статуса |
| `sync_yandex_delivery_status` | Синхронизация статусов Яндекс Доставки | Каждые 5 минут |
| `generate_daily_report` | Ежедневный отчёт: заказы, выручка, топ товары | Каждый день в 9:00 |
| `update_promo_codes_expiry` | Проверка истёкших промокодов | Каждый час |
| `release_expired_reservations` | Освобождение истёкших резервов заказов | Каждый час |

#### Запуск Celery worker
```bash
# В контейнере
docker compose exec celery-worker celery -A coffee_shop worker -l info

# Локально
celery -A coffee_shop worker -l info
```

#### Проверка статуса Celery
```bash
docker compose exec celery-worker celery -A coffee_shop inspect ping
```

#### Настройка Celery Beat (periodic tasks)
Настройка находится в `settings/base.py`:
```python
CELERY_BEAT_SCHEDULE = {
    'sync-yandex-delivery': {
        'task': 'coffee_shop.tasks.sync_yandex_delivery_status',
        'schedule': timedelta(minutes=5),
    },
    'generate-daily-report': {
        'task': 'coffee_shop.tasks.generate_daily_report',
        'schedule': crontab(hour=9, minute=0),
    },
    'update-promo-codes': {
        'task': 'coffee_shop.tasks.update_promo_codes_expiry',
        'schedule': crontab(minute=0),
    },
    'release-expired-reservations': {
        'task': 'coffee_shop.tasks.release_expired_reservations',
        'schedule': crontab(minute=0),
    },
}

```

## 🔒 Безопасность

### Реализованные меры безопасности

| Мера | Статус | Описание |
|------|--------|----------|
| CSRF защита | ✅ | Django по умолчанию |
| XSS защита | ✅ | Auto-escape в шаблонах |
| SQL-инъекции | ✅ | ORM, raw-queries только с params |
| HSTS | ✅ | Strict-Transport-Security |
| CSP (Content Security Policy) | ✅ | Ограничение источников контента |
| X-Frame-Options | ✅ | DENY |
| X-XSS-Protection | ✅ | 1; mode=block |
| X-Content-Type-Options | ✅ | nosniff |
| Rate limiting | ✅ | Redis-based на критичные эндпоинты |
| Секреты в .env | ✅ | Через Docker secrets |

### Rate limiting

Реализован через `middleware.py` с использованием Redis:

| Эндпоинт | Лимит | Период |
|----------|-------|--------|
| `/cart/add/` | 30 запросов | 60 секунд |
| `/checkout/` | 10 запросов | 60 секунд |
| `/pay/` | 5 запросов | 60 секунд |

### Best practices
- Секреты только в `.env` / Docker secrets
- CSRF защита включена по умолчанию
- HTTPS-only cookies для production
- Валидация mime-type при загрузке файлов
- Structured JSON logging для аудита

---

## 💾 Бэкапы и восстановление

### Бэкап данных

#### Автоматический бэкап
```bash
# Использование скрипта backup.sh
./backup.sh

# Или вручную
pg_dump -U coffee_shop coffee_shop > backup_$(date +%Y%m%d_%H%M%S).sql
```

#### Что бэкапится
- PostgreSQL база данных
- Медиафайлы (media/)
- Настройки (опционально)

#### Ротация бэкапов
- Хранятся последние 7 копий
- Автоматическое удаление старых бэкапов

### Восстановление данных

#### Использование скрипта restore.sh
```bash
# Восстановление из бэкапа
./restore.sh путь/к/бэкапу.sql
```

#### Ручное восстановление
```bash
# Восстановление БД
psql -U coffee_shop coffee_shop < backup_file.sql

# Восстановление медиафайлов
tar -xzf media_backup.tar.gz -C /path/to/media/
```

### Бэкап через Docker
```bash
# Бэкап БД из контейнера
docker compose exec db pg_dump -U coffee_shop coffee_shop > backup.sql

# Бэкап медиафайлов
docker compose run --rm web tar czf /tmp/media_backup.tar.gz media/
```

### Чек-лист восстановления
1. ✅ Остановить сервисы
   ```bash
   docker compose down
   ```
2. ✅ Восстановить БД
   ```bash
   docker compose exec -T db psql -U coffee_shop coffee_shop < backup.sql
   ```
3. ✅ Восстановить медиафайлы
   ```bash
   docker compose cp media_backup.tar.gz web:/app/media/
   docker compose exec web tar xzf media_backup.tar.gz -C /app/media/
   ```
4. ✅ Запустить сервисы
   ```bash
   docker compose up -d
   ```
5. ✅ Проверить работоспособность

---

## 📊 Мониторинг

### Healthcheck endpoints

#### `/health/`
Проверяет работоспособность сервиса. Возвращает JSON:
```json
{
    "status": "ok",
    "timestamp": "2023-10-15T12:34:56.789Z"
}
```

### Docker healthchecks

| Сервис | Healthcheck | Период |
|--------|-------------|--------|
| web | `curl -f http://localhost:8000/health/` | 30с |
| nginx | `curl -f http://localhost:80/` | 15с |
| db | `pg_isready -U coffee_shop` | 5с |
| redis | `redis-cli ping` | 10с |
| celery-worker | `celery inspect ping` | 30с |

### Logging

#### Structured JSON logging
Настроен в `settings/base.py`:
```python
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'fmt': '%(asctime)s %(levelname)s %(name)s %(message)s',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'json',
        },
    },
}
```

#### Просмотр логов
```bash
# Логи веб-сервиса
docker compose logs -f web

# Логи celery worker
docker compose logs -f celery-worker

# Логи nginx
docker compose logs -f nginx
```

### Метрики и алертинг

#### Мониторинг через Docker Compose
- Restart policy: `unless-stopped` для всех сервисов
- Автоматический перезапуск при падении
- Healthchecks для отслеживания состояния

#### Генерация отчётов
```bash
# Ежедневный отчёт через Celery Beat
docker compose exec celery-worker celery -A coffee_shop apply_async --args=[generate_daily_report]
```

#### Ручная проверка
```bash
# Проверка контейнеров
docker compose ps

# Проверка health status
docker inspect --format='{{ .State.Health.Status }}' <container_id>

# Проверка логов ошибок
docker compose logs --tail=100 web | grep ERROR
```

### Рекомендуемые инструменты мониторинга
- Prometheus + Grafana для метрик
- ELK Stack (Elasticsearch, Logstash, Kibana) для логов
- Sentry для отслеживания ошибок
- UptimeRobot для внешнего мониторинга
