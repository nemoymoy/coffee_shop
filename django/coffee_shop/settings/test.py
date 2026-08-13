"""
Test settings for coffee_shop project.
"""
from .dev import *

DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': 'coffee_shop_test',
        'USER': 'coffee_shop',
        'PASSWORD': 'change-me-dev',
        'HOST': 'db',
        'PORT': '5432',
    }
}

# Disable debug toolbar in tests
if 'debug_toolbar' in INSTALLED_APPS:
    INSTALLED_APPS.remove('debug_toolbar')
