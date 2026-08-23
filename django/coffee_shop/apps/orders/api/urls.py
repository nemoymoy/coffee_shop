"""URLs for orders API."""
from django.urls import path

from coffee_shop.apps.orders.api.views import delivery_locations_api

app_name = 'orders_api'

urlpatterns = [
    path('delivery/locations/', delivery_locations_api, name='delivery_locations'),
]
