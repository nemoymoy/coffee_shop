"""
Development settings for coffee_shop project.
"""
from .base import *

DEBUG = True
SECRET_KEY = 'dev-secret-key-change-in-production-1234567890'
ALLOWED_HOSTS = ['*', 'localhost', '127.0.0.1']

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'coffee_shop_dev',
        'USER': 'coffee_shop',
        'PASSWORD': 'change-me-dev',
        'HOST': 'localhost',
        'PORT': '5432',
    }
}

# Email (console backend for dev)
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} {module} {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG',
    },
}

# Debug Toolbar (optional)
if 'debug_toolbar' in INSTALLED_APPS:
    MIDDLEWARE.insert(0, 'debug_toolbar.middleware.DebugToolbarMiddleware')
