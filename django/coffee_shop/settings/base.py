"""
Django settings for coffee_shop project.
"""
import environ
import os
from pathlib import Path
from datetime import timedelta
from celery.schedules import crontab

# Settings from environment or defaults
DEBUG = os.environ.get('DEBUG', 'False').lower() in ('true', '1', 'yes')
SECRET_KEY = os.environ.get('SECRET_KEY', 'change-me-in-production')
ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1')
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://postgres:postgres@db:5432/coffee_shop')
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
DOMAIN = os.environ.get('DOMAIN', 'localhost')

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Security
SECRET_KEY = SECRET_KEY
DEBUG = DEBUG
ALLOWED_HOSTS = ALLOWED_HOSTS.split(',')
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')

# File upload limits
DATA_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB
FILE_UPLOAD_MAX_MEMORY_SIZE = 10 * 1024 * 1024  # 10 MB

# HSTS — только для production
if not DEBUG:
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = True
    SECURE_HSTS_PRELOAD = True

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'django.contrib.sites',

    # Third party
    'rest_framework',
    'corsheaders',
    'crispy_forms',
    'crispy_bootstrap5',
    'django_filters',
    'django_celery_beat',
    'django_celery_results',

    # Local
    'coffee_shop.apps.catalog',
    'coffee_shop.apps.orders',
    'coffee_shop.apps.users',
    'coffee_shop.apps.news',

    # Social Auth
    'social_django',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'coffee_shop.middleware.SecurityHeadersMiddleware',
    'corsheaders.middleware.CorsMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    'coffee_shop.middleware.RequestLoggingMiddleware',
    'coffee_shop.middleware.RateLimitingMiddleware',
]

ROOT_URLCONF = 'coffee_shop.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'coffee_shop' / 'templates'],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
                'coffee_shop.context_processors.yandex_metrika',
            ],
        },
    },
]

WSGI_APPLICATION = 'coffee_shop.wsgi.application'
ASGI_APPLICATION = 'coffee_shop.asgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': environ.urlparse(DATABASE_URL).path[1:],
        'USER': environ.urlparse(DATABASE_URL).username,
        'PASSWORD': environ.urlparse(DATABASE_URL).password,
        'HOST': environ.urlparse(DATABASE_URL).hostname,
        'PORT': 5432,
    }
}

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

# Internationalization
LANGUAGE_CODE = 'ru-ru'
TIME_ZONE = 'Europe/Moscow'
USE_I18N = True
USE_TZ = True

SITE_ID = 1

# Static files
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
STATICFILES_DIRS = [BASE_DIR / 'static']

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# Crispy forms
CRISPY_ALLOWED_TEMPLATE_PACKS = 'bootstrap5'
CRISPY_TEMPLATE_PACK = 'bootstrap5'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.AllowAny',
    ],
    'DEFAULT_FILTER_BACKENDS': [
        'django_filters.rest_framework.DjangoFilterBackend',
        'rest_framework.filters.SearchFilter',
        'rest_framework.filters.OrderingFilter',
    ],
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 20,
}

# Celery
CELERY_BROKER_URL = REDIS_URL
CELERY_RESULT_BACKEND = 'django-db'
CELERY_CACHE_BACKEND = 'default'
CELERY_TIMEZONE = TIME_ZONE
CELERY_ACCEPT_CONTENT = ['json']
CELERY_TASK_SERIALIZER = 'json'
CELERY_RESULT_SERIALIZER = 'json'
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

# Redis
REDIS_URL = REDIS_URL

# Email — SMTP для production, console для dev
if DEBUG:
    EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
else:
    EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
    EMAIL_HOST = 'smtp.rusender.ru'
    EMAIL_PORT = 465
    EMAIL_USE_SSL = True
    EMAIL_HOST_USER = os.environ.get('RUSENDER_USERNAME', '')
    EMAIL_HOST_PASSWORD = os.environ.get('RUSENDER_PASSWORD', '')
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'noreply@' + DOMAIN)

# YooKassa (ЮКасса)
YOOKASSA_MERCHANT_ID = os.environ.get('YOOKASSA_MERCHANT_ID', '')
YOOKASSA_API_KEY = os.environ.get('YOOKASSA_API_KEY', '')
YOOKASSA_WEBHOOK_SECRET = os.environ.get('YOOKASSA_WEBHOOK_SECRET', '')
YOOKASSA_RETURN_URL = os.environ.get('YOOKASSA_RETURN_URL', '')
YOOKASSA_TEST_MODE = os.environ.get('YOOKASSA_TEST_MODE', 'true').lower() in ('1', 'true', 'yes')

# Legacy aliases for backward compatibility
YOOMONEY_SHOP_ID = YOOKASSA_MERCHANT_ID
YOOMONEY_SECRET_KEY_1 = YOOKASSA_API_KEY
YOOMONEY_SECRET_KEY_2 = YOOKASSA_WEBHOOK_SECRET

# Yandex Delivery
YANDEX_DELIVERY_CLIENT_ID = os.environ.get('YANDEX_DELIVERY_CLIENT_ID', '')
YANDEX_DELIVERY_CLIENT_SECRET = os.environ.get('YANDEX_DELIVERY_CLIENT_SECRET', '')
YANDEX_REDIRECT_URI = os.environ.get('YANDEX_REDIRECT_URI', 'http://localhost:8000/delivery/callback/')
YANDEX_FROM_CITY = os.environ.get('YANDEX_FROM_CITY', 'moscow')
YANDEX_FROM_STREET = os.environ.get('YANDEX_FROM_STREET', '')
YANDEX_FROM_HOUSE = os.environ.get('YANDEX_FROM_HOUSE', '')
YANDEX_FROM_APT = os.environ.get('YANDEX_FROM_APT', '')

# Yandex Metrika
YANDEX_METRIKA_ID = os.environ.get('YANDEX_METRIKA_ID', '')
YANDEX_METRIKA_WEBVIEWER = os.environ.get('YANDEX_METRIKA_WEBVIEWER', '').lower() in ('1', 'true', 'yes')

# Logging — JSON format for structured logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'json': {
            '()': 'pythonjsonlogger.jsonlogger.JsonFormatter',
            'fmt': '%(asctime)s %(levelname)s %(name)s %(message)s',
        },
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'json' if not DEBUG else 'verbose',
        },
        'file': {
            'class': 'logging.FileHandler',
            'filename': BASE_DIR / 'logs' / 'django.log',
            'formatter': 'json',
        },
    },
    'root': {
        'handlers': ['console', 'file'],
        'level': 'INFO',
    },
    'loggers': {
        'django': {
            'handlers': ['console'],
            'level': 'WARNING',
            'propagate': True,
        },
        'coffee_shop': {
            'handlers': ['console', 'file'],
            'level': 'DEBUG',
            'propagate': False,
        },
    },
}

# Ensure logs directory exists
logs_dir = BASE_DIR / 'logs'
if not logs_dir.exists():
    logs_dir.mkdir(parents=True)

# ------------------------------------------------------------------
# Yandex OAuth 2.0 (User Authentication)
# ------------------------------------------------------------------
YANDEX_OAUTH_CLIENT_ID = os.environ.get('YANDEX_OAUTH_CLIENT_ID', '')
YANDEX_OAUTH_CLIENT_SECRET = os.environ.get('YANDEX_OAUTH_CLIENT_SECRET', '')
YANDEX_OAUTH_AUTHORIZATION_URL = 'https://oauth.yandex.ru/authorize'
YANDEX_OAUTH_TOKEN_URL = 'https://oauth.yandex.ru/token'
YANDEX_OAUTH_PROFILE_URL = 'https://login.yandex.ru/info'
YANDEX_OAUTH_REDIRECT_URI = os.environ.get('YANDEX_OAUTH_REDIRECT_URI', 'http://localhost:8000/accounts/oauth/complete/yandex/')

# social-auth
AUTHENTICATION_BACKENDS = [
    'coffee_shop.apps.users.backends.YandexOAuth',
    'django.contrib.auth.backends.ModelBackend',
]

LOGIN_URL = 'users:login'
LOGIN_REDIRECT_URL = 'catalog:catalog'
LOGOUT_URL = 'users:logout'

SOCIAL_AUTH_URL_NAMESPACE = None
SOCIAL_AUTH_LOGIN_REDIRECT_URL = 'catalog:catalog'
SOCIAL_AUTH_LOGIN_ERROR_URL = 'users:login'
SOCIAL_AUTH_LOGIN_URL = 'accounts/login/yandex/'

SOCIAL_AUTH_YANDEX_KEY = YANDEX_OAUTH_CLIENT_ID
SOCIAL_AUTH_YANDEX_SECRET = YANDEX_OAUTH_CLIENT_SECRET
SOCIAL_AUTH_YANDEX_AUTHORIZATION_URL = YANDEX_OAUTH_AUTHORIZATION_URL
SOCIAL_AUTH_YANDEX_ACCESS_TOKEN_URL = YANDEX_OAUTH_TOKEN_URL
SOCIAL_AUTH_YANDEX_USER_PROFILE_URL = YANDEX_OAUTH_PROFILE_URL
SOCIAL_AUTH_YANDEX_REDIRECT_URI = YANDEX_OAUTH_REDIRECT_URI

SOCIAL_AUTH_PIPELINE = (
    'social_core.pipeline.social_auth.social_details',
    'social_core.pipeline.social_auth.social_uid',
    'social_core.pipeline.social_auth.auth_allowed',
    'social_core.pipeline.social_auth.social_user',
    'social_core.pipeline.user.get_username',
    'social_core.pipeline.user.create_user',
    'social_core.pipeline.social_auth.associate_user',
    'social_core.pipeline.social_auth.load_extra_data',
    'social_core.pipeline.user.user_details',
    'coffee_shop.apps.users.pipeline.auto_link_existing_user',
    'coffee_shop.apps.users.pipeline.create_personal_data_consent',
)

# Add social_django context processors
TEMPLATES[0]['OPTIONS']['context_processors'].append(
    'social_django.context_processors.backends',
)
