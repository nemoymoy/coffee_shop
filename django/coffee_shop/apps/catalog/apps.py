# Catalog app
from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'coffee_shop.apps.catalog'
    verbose_name = 'Каталог'
