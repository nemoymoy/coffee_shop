"""
WSGI config for coffee_shop project.
"""
import os

from django.core.wsgi import get_wsgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'coffee_shop.settings.dev')

application = get_wsgi_application()
