"""
Development settings for coffee_shop project.
"""
from .base import *

DEBUG = True
SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-production-1234567890')
ALLOWED_HOSTS = ['*', 'localhost', '127.0.0.1']

# Enable for pytest (conftest adds django/ to sys.path)
TESTING = True

# Email (SMTP for dev testing)
EMAIL_BACKEND = 'django.core.mail.backends.smtp.EmailBackend'
EMAIL_HOST = os.environ.get('EMAIL_HOST', 'smtp.rusender.ru')
EMAIL_PORT = int(os.environ.get('EMAIL_PORT', '465'))
EMAIL_USE_SSL = os.environ.get('EMAIL_USE_SSL', 'True').lower() in ('true', '1', 'yes')
# Поддерживаем оба варианта имен переменных
EMAIL_HOST_USER = os.environ.get('EMAIL_HOST_USER') or os.environ.get('RUSENDER_USERNAME', '')
EMAIL_HOST_PASSWORD = os.environ.get('EMAIL_HOST_PASSWORD') or os.environ.get('RUSENDER_PASSWORD', '')
EMAIL_FROM = os.environ.get('EMAIL_FROM', 'noreply@localhost')

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
