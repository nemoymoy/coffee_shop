"""
URL configuration for coffee_shop project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from . import views

urlpatterns = [
    path('admin/', admin.site.urls),
    path('health/', views.health_check, name='health'),
    path('', views.home, name='home'),
    path('catalog/', include('coffee_shop.apps.catalog.urls', namespace='catalog')),
    path('cart/', include('coffee_shop.apps.orders.urls', namespace='cart')),
    path('', include('coffee_shop.apps.orders.urls', namespace='checkout')),
    # Catalog API
    path('api/catalog/', include('coffee_shop.apps.catalog.api.urls', namespace='catalog_api')),
    # News API
    path('api/news/', include('coffee_shop.apps.news.api.urls', namespace='news_api')),
    path('about/', views.about, name='about'),
    path('news/', include('coffee_shop.apps.news.urls', namespace='news')),
    path('news/list/', views.news_view, name='news'),
    # Users
    path('accounts/', include('coffee_shop.apps.users.urls', namespace='users')),
    # Social Auth (Yandex OAuth)
    path('accounts/oauth/', include('social_django.urls')),  # type: ignore[call-arg]
]

if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
