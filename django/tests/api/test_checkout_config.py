"""Tests for checkout config API endpoint."""
import pytest
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status


pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


class TestCheckoutConfigView:
    """Тесты для /api/checkout/config/ endpoint."""

    def test_authenticated_user_can_get_config(self, client, user):
        """Авторизованный пользователь может получить конфиг."""
        client.login(username='testuser', password='testpass123')
        response = client.get(reverse('orders:checkout_config'))
        assert response.status_code == status.HTTP_200_OK
        data = response.json()
        assert 'YANDEX_GEOCODER_API_KEY' in data
        assert 'YANDEX_JAVASCRIPT_API_KEY' in data

    def test_anonymous_user_rejected(self, client):
        """Анонимный пользователь не может получить конфиг (редирект на логин)."""
        response = client.get(reverse('orders:checkout_config'))
        # @login_required возвращает 302 redirect на LOGIN_URL
        assert response.status_code == status.HTTP_302_FOUND
        assert '/accounts/login/' in response.url
