"""URL routing for news API."""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import NewsViewSet, PromotionViewSet

app_name = 'news_api'

router = DefaultRouter()
router.register(r'news', NewsViewSet)
router.register(r'promotions', PromotionViewSet)

urlpatterns = [
    path('', include(router.urls)),
]
