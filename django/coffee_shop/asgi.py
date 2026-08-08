"""
ASGI config for coffee_shop project.
"""
import os

from django.core.asgi import get_asgi_application

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'coffee_shop.settings.dev')

application = get_asgi_application()
