# Coffee Shop — Кофейня с доставкой и онлайн-заказами

[![Python 3.12](https://img.shields.io/badge/Python-3.12-blue.svg)](https://python.org)
[![Django 4.2 / 6.1](https://img.shields.io/badge/Django-4.2--6.1-092E20.svg)](https://djangoproject.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-336791.svg)](https://postgresql.org)
[![Redis](https://img.shields.io/badge/Redis-Alpine-DC382D.svg)](https://redis.io)
[![DRF](https://img.shields.io/badge/DRF-3.18+-092E20.svg)](https://www.django-rest-framework.org)

---

## 📋 Содержание

- [Описание](#-описание)
- [Основные возможности](#-основные-возможности)
- [Технологический стек](#-технологический-стек)
- [Структура проекта](#-структура-проекта)
- [Требования](#-требования)
- [Установка и запуск](#-установка-и-запуск)
- [Deployment guide](#deployment-guide)
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
- **Корзина** с промокодами (AJAX-валидация), резервированием товаров и автоматическим расчётом стоимости
- **Управление остатками**: резервирование при оформлении, списание при оплате, освобождение при отмене
- **Оформление заказа** с валидацией через Django Forms, выбором доставки (самовывоз или Яндекс Доставка)
- **Статусы заказа**: Новый → Ожидает оплаты → В обработке → Готов → Доставлен / Отменён
- **Резервирование товаров**: автоматический сброс резерва при истечении таймаута (Celery)
- **Оплата** через ЮКасса (онлайн) или наличными при получении
- **Личный кабинет** с историей заказов и статусами
- **Отзывы** на товары
- **Новости** — публикации новостей кофейни с пагинацией и поиском
- **Акции** — список активных спецпредложений с датами начала и окончания

### 🎨 Админ-панель
- Управление товарами, категориями, заказами, промокодами, отзывами
- Массовые операции (изменение статусов, экспорт в CSV)
- Визуальные бейджи для статусов и оценок SCA
- Предпросмотр изображений товаров
- Фильтры по статусу, категории, дате, наличию

### 🛠 Технические возможности
- **Адаптивный дизайн** (Bootstrap 5)
- **AJAX-корзина** без перезагрузки страницы
- **REST API** для каталога (Products, Categories, Reviews)
- **Интеграция с Яндекс Доставкой** (расчёт стоимости, создание заказов)
- **Платежи через ЮКасса** с webhook-обработкой
- **Email-уведомления** (SendGrid)
- **Фоновые задачи** через Celery + Redis
- **Rate limiting** на критичные эндпоинты
- **Structured JSON logging**
- **News API** — REST API для новостей и акций с поиском, фильтрацией и сортировкой

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
| **API** | Django REST Framework | 3.18+ |
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
│   │   │   │   ├── serializers.py # DRF сериализаторы: Category, Product, Review
│   │   │   │   ├── api/           # REST API endpoints
│   │   │   │   │   ├── views.py   # ViewSet: Product, Category, Review
│   │   │   │   │   └── urls.py    # /api/catalog/ маршруты
│   │   │   │   ├── views.py       # View: каталог, товары
│   │   │   │   ├── urls.py        # URL каталога
│   │   │   │   └── admin.py       # Админ-категории и товары
│   │   │   │
│   │   │   ├── news/              # Новости и акции
│   │   │   │   ├── models/        # Модели: News, Promotion
│   │   │   │   ├── services/      # Сервисы: NewsService, PromotionService
│   │   │   │   ├── forms/         # Формы: NewsForm, PromotionForm
│   │   │   │   ├── serializers.py # DRF сериализаторы: News, Promotion
│   │   │   │   ├── api/           # REST API endpoints
│   │   │   │   │   ├── views.py   # ViewSet: News, Promotion
│   │   │   │   │   └── urls.py    # /api/news/ маршруты
│   │   │   │   ├── views.py       # View: новости, акции
│   │   │   │   ├── urls.py        # URL новостей
│   │   │   │   └── admin.py       # Админ-новости и акции
│   │   │   ├── orders/            # Заказы
│   │   │   │   ├── models/        # Модели: Order, OrderItem, PromoCode
│   │   │   │   ├── services/      # Сервисы: Stock, Delivery, Payment, OAuth, Promo
│   │   │   │   ├── forms/         # Формы: CheckoutForm, OrderForm (с промокодом)
│   │   │   │   ├── serializers.py # DRF сериализаторы: OrderDetail, OrderList, PromoCode
│   │   │   │   ├── views.py       # View: корзина, оформление, промокод, webhook
│   │   │   │   ├── urls.py        # URL заказов (+ /promo/check/)
│   │   │   │   └── admin.py       # Админ-заказы и промокоды
│   │   │   │
│   │   │   ├── users/             # Пользователи
│   │   │   │   ├── forms/         # Формы: UserUpdateForm, UserRegistrationForm
│   │   │   │   ├── services/      # Сервисы: UserService
│   │   │   │   ├── views.py       # View: логин, регистрация
│   │   │   │   ├── urls.py        # URL: /accounts/*
│   │   │   │   ├── serializers.py # DRF сериализаторы
│   │   │   │   └── admin.py       # Админ: UserAdmin переопределён
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
- Открытые порты: 80 (HTTP), 443 (HTTPS), 22 (SSH)

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

## Deployment guide {#deployment-guide}

Полная инструкция по развёртыванию на удалённом Ubuntu-сервере.

#### Шаг 1: Подготовка сервера

```bash
# Обновить систему
sudo apt update && sudo apt upgrade -y

# Установить Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# Установить Docker Compose plugin
sudo apt install docker-compose-plugin -y

# Добавить пользователя в группу docker
sudo usermod -aG docker $USER
newgrp docker

# Проверить установку
docker --version
docker compose version
```

#### Шаг 2: Настроить брандмауэр

```bash
# Разрешить необходимые порты
sudo ufw allow 22/tcp   # SSH
sudo ufw allow 80/tcp   # HTTP
sudo ufw allow 443/tcp  # HTTPS
sudo ufw enable
```

#### Шаг 3: Клонировать проект

```bash
# Подключиться к серверу
ssh user@your_server_ip

# Клонировать репозиторий
cd ~
git clone https://github.com/your-username/coffee_shop.git
cd coffee_shop
```

#### Шаг 4: Настроить переменные окружения

```bash
# Скопировать шаблон
cp .env.example .env

# Отредактировать файл
nano .env
```

**Ключевые переменные для production:**

```bash
# Django
SECRET_KEY=your-super-secret-key-at-least-50-chars-long
DEBUG=False
DOMAIN=yourdomain.com
ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com

# Database
DATABASE_URL=postgresql://coffee_shop:strong-password@db:5432/coffee_shop
POSTGRES_DB=coffee_shop
POSTGRES_USER=coffee_shop
POSTGRES_PASSWORD=strong-password

# YooKassa
YOOKASSA_MERCHANT_ID=your-shop-id
YOOKASSA_API_KEY=your-secret-key
YOOKASSA_WEBHOOK_SECRET=your-webhook-secret
YOOKASSA_RETURN_URL=https://yourdomain.com/pay/callback/
YOOKASSA_TEST_MODE=false

# Email
SENDGRID_PASSWORD=your-sendgrid-api-key
EMAIL_FROM=noreply@yourdomain.com
```

#### Шаг 5: Настроить Nginx

Отредактируйте `nginx/sites-available/coffee.conf`:

```nginx
server {
    listen 80;
    server_name yourdomain.com;  # ← измените на свой домен

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass http://web:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /usr/share/nginx/html/static/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /usr/share/nginx/html/media/;
        expires 7d;
    }
}
```

#### Шаг 6: Запустить проект

```bash
# Собрать и запустить все сервисы
docker compose up -d --build

# Проверить статус
docker compose ps

# Проверить логи
docker compose logs -f web
```

#### Шаг 7: Применить миграции и собрать статику

```bash
# Миграции
docker compose exec web python manage.py migrate

# Создание суперпользователя
docker compose exec web python manage.py createsuperuser

# Сборка статики
docker compose exec web python manage.py collectstatic --noinput --clear
```

#### Шаг 8: Настроить SSL (Let's Encrypt)

```bash
# Получить сертификаты
docker compose exec certbot certbot certonly \
    --webroot \
    --webroot-path=/var/www/certbot \
    --email your-email@example.com \
    --agree-tos \
    -d yourdomain.com \
    -d www.yourdomain.com

# Перезапустить Docker Compose для применения SSL
docker compose up -d
```

> Сертификаты будут автоматически обновляться через контейнер certbot.

#### Шаг 9: Проверить работу

```bash
# Проверить health
curl http://yourdomain.com/health/

# Открыть сайт
open http://yourdomain.com

# Админ-панель
open http://yourdomain.com/admin/
```

#### Полезные команды

```bash
# Просмотр логов
docker compose logs -f web          # логи Django
docker compose logs -f nginx        # логи Nginx
docker compose logs -f celery-worker # фоновые задачи

# Остановка сервисов
docker compose down

# Перезапуск
docker compose restart

# Проверка контейнеров
docker compose ps
```

#### ⚠️ Важные моменты

1. **Секреты в `.env`** — никогда не публикуйте этот файл
2. **DEBUG=False** — обязательно для production
3. **Домен** — проект ожидает, что к нему идут обращения по доменному имени (для SSL и CORS)
4. **Фоновые задачи** — Celery запускается автоматически через `docker compose`
5. **Статика и медиа** — хранятся в Docker-томах `static_data` и `media_data`

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

### REST API (`/api/catalog/`)
| Эндпоинт | Метод | Описание |
|----------|-------|----------|
| `/api/catalog/categories/` | GET | Список категорий |
| `/api/catalog/categories/{id}/` | GET | Детали категории |
| `/api/catalog/categories/{id}/products/` | GET | Товары категории |
| `/api/catalog/products/` | GET | Список товаров |
| `/api/catalog/products/{id}/` | GET | Детали товара |
| `/api/catalog/products/{id}/reviews/` | GET | Отзывы товара |
| `/api/catalog/products/featured/` | GET | Рекомендуемые товары (SCA ≥ 85) |
| `/api/catalog/reviews/` | GET, POST | Список / создание отзывов |
| `/api/catalog/reviews/{id}/approve/` | POST | Одобрить отзыв |

### REST API (`/api/news/`)
| Эндпоинт | Метод | Описание |
|----------|-------|----------|
| `/api/news/news/` | GET | Список опубликованных новостей |
| `/api/news/news/{id}/` | GET | Детали новости |
| `/api/news/promotions/` | GET | Список активных акций |
| `/api/news/promotions/{id}/` | GET | Детали акции |

**Фильтрация и поиск:**
- `?search=keyword` — поиск по заголовку и содержанию
- `?ordering=-published_at` — сортировка (published_at, created_at)
- `?is_published=true` — фильтрация по статусу

### Корзина и заказы
| Эндпоинт | Описание |
|----------|----------|
| `/cart/` | Корзина |
| `/cart/add/` (POST) | Добавить товар в корзину |
| `/promo/check/` (POST) | AJAX-валидация промокода |
| `/checkout/` | Оформление заказа |
| `/checkout/success/<order_id>/` | Страница успешного заказа |
| `/cart/webhook/` (POST) | ЮКасса webhook-обработчик |

### Пользователи
| Эндпоинт | Описание |
|----------|----------|
| `/accounts/login/` | Авторизация |
| `/accounts/logout/` | Выход |
| `/accounts/register/` | Регистрация нового пользователя |
| `/accounts/dashboard/` | Личный кабинет (история заказов) |
| `/accounts/profile/` | Редактирование профиля + смена пароля |

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
| GET | `/api/catalog/categories/` | Список категорий |
| GET | `/api/catalog/products/` | Список товаров (DRF ViewSet) |
| GET | `/api/catalog/products/{id}/` | Детали товара |
| GET | `/api/catalog/products/featured/` | Рекомендуемые товары (SCA ≥ 85) |
| GET | `/api/catalog/products/{id}/reviews/` | Отзывы товара |
| POST | `/api/catalog/reviews/` | Создать отзыв (авторизация) |
| POST | `/api/catalog/reviews/{id}/approve/` | Одобрить отзыв |

### REST API (`/api/news/`)
| Метод | Эндпоинт | Описание |
|-------|----------|----------|
| GET | `/api/news/news/` | Список опубликованных новостей |
| GET | `/api/news/news/{id}/` | Детали новости |
| GET | `/api/news/promotions/` | Список активных акций |
| GET | `/api/news/promotions/{id}/` | Детали акции |
| GET | `/api/news/news/?search=keyword` | Поиск по заголовку/содержанию |
| GET | `/api/news/news/?ordering=-published_at` | Сортировка |
| GET | `/api/news/promotions/?is_active=true` | Фильтрация по активности |

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
pytest tests/forms/
```

### Тесты для users app
```bash
# Все тесты users app
pytest tests/views/test_users.py
pytest tests/forms/test_users.py
pytest tests/services/test_users.py

# С покрытием
pytest tests/views/test_users.py --cov=coffee_shop.apps.users --cov-report=term-missing
```

### Покрытие тестами
- **views**: login, register, logout, dashboard, profile, смена пароля
- **forms**: UserUpdateForm, UserRegistrationForm (валидация, конфликты)
- **services**: UserService.create_user, get_user_profile, update_user_profile

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
│   ├── test_checkout.py
│   └── test_users.py                      # Тесты: login, register, profile, dashboard
├── api/                                 # Тесты API
│   ├── test_catalog_api.py              # Каталог API (Product, Category, Review)
│   ├── test_serializers.py              # DRF сериализаторы
│   ├── test_yandex_delivery_api.py
│   ├── test_payment_gateway.py
│   └── news/                              # Тесты news API
│       ├── test_api.py                  # News API, Promotion API
├── news/                                # Тесты news app
│   ├── test_models.py                   # News, Promotion модели
│   ├── test_services.py                 # NewsService, PromotionService
│   ├── test_views.py                    # news_list, news_detail, promotions_list
│   └── test_forms.py                    # NewsForm, PromotionForm
└── forms/                               # Тесты форм
    ├── test_order_forms.py
    ├── test_coffee_form.py              # CoffeeForm: вес, помол, brewing_method
    ├── test_product_form.py             # ProductForm: фильтры каталога
    └── test_users.py                      # Тесты: UserUpdateForm, UserRegistrationForm
```

### Ключевые сценарии тестирования
- Валидация веса (кратность 50 г)
- brewing_method при coffee_form=ground
- Контроль остатков и резервирование товаров (StockService)
- Расчёт цены
- Моки Яндекс Доставки
- Промокоды (валидация, применение скидки, подсчёт лимитов, PromoService)
- Конкурентные заказы
- DRF сериализация (OrderDetail, OrderList, PromoCode)
- REST API: сериализация, фильтрация, создание отзывов
- **news**: published news filtering, future news hiding, promotion date validation, news search
- **news API**: CRUD, search, ordering, list vs detail fields

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
- ✅ Status badges с цветовой кодировкой (new, awaiting_payment, in_progress, ready, delivered, cancelled)
- ✅ Inline-редактирование OrderItem
- ✅ Массовое изменение статусов (mark_awaiting_payment, mark_in_progress, mark_ready, mark_delivered, mark_cancelled)
- ✅ Экспорт заказов в CSV
- ✅ Предпросмотр информации о доставке (Yandex Delivery)
- ✅ Управление промокодами (валидация, активация/деактивация, отслеживание лимитов)
- ✅ Поле reserved_at для отслеживания резервирования

#### Управление пользователями (users)
- ✅ Редактирование профилей (first_name, last_name, email, username)
- ✅ Управление правами доступа (staff, superuser, is_active)
- ✅ Фильтры по дате регистрации, группе, роли
- ✅ Смена пароля через админ-панель

#### Управление категориями (catalog)
- ✅ Вложенные категории
- ✅ Фильтры по активности
- ✅ Предпросмотр товаров

#### Управление отзывами (catalog)
- ✅ Модерация отзывов (approve/unapprove)
- ✅ Фильтры по рейтингу

#### Управление новостями и акциями (news)
- ✅ CRUD для новостей и акций
- ✅ Фильтры по опубликованности и активности
- ✅ Поиск по заголовку и содержанию
- ✅ Автоматическая генерация slug из заголовка
- ✅ Поля created_at / updated_at для отслеживания изменений
- ✅ Акции с датами начала/окончания и флагом текущей акции (is_current)

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
| `release_expired_reservations` | Освобождение резервов товаров для неоплаченных заказов (status=awaiting_payment, timeout=30 мин) | Каждый час |

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
| Webhook HMAC-SHA256 | ✅ | ЮКасса webhook верификация через `YOOKASSA_WEBHOOK_SECRET` |

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
