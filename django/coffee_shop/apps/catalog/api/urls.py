"""URLs for catalog API."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from coffee_shop.apps.catalog.api.views import (
    CategoryViewSet,
    ProductViewSet,
    ReviewViewSet,
)

router = DefaultRouter()
router.register(r'categories', CategoryViewSet, basename='category')
router.register(r'products', ProductViewSet, basename='product')
router.register(r'reviews', ReviewViewSet, basename='review')

app_name = 'catalog_api'

urlpatterns = [
    path('', include(router.urls)),
]
