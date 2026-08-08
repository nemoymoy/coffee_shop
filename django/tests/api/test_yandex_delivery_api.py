"""Tests for Yandex Delivery API mock integration."""
import pytest
from unittest.mock import patch, MagicMock
from coffee_shop.apps.orders.services.yandex_oauth import YandexOAuth


pytestmark = pytest.mark.django_db


class TestYandexOAuth:
    """Тесты OAuth сервиса."""

    def test_is_configured_no_credentials(self):
        with patch.object(YandexOAuth, 'CLIENT_ID', ''), \
             patch.object(YandexOAuth, 'CLIENT_SECRET', ''):
            oauth = YandexOAuth()
            assert oauth.is_configured() is False

    def test_get_authorization_url_no_credentials(self):
        with patch.object(YandexOAuth, 'CLIENT_ID', ''), \
             patch.object(YandexOAuth, 'CLIENT_SECRET', ''):
            oauth = YandexOAuth()
            url = oauth.get_authorization_url(state='test-state')
            assert 'https://oauth.yandex.ru/authorize' in url
            assert 'client_id=' in url
            assert 'response_type=code' in url

    def test_exchange_code_mock(self):
        with patch.object(YandexOAuth, 'CLIENT_ID', ''), \
             patch.object(YandexOAuth, 'CLIENT_SECRET', ''):
            oauth = YandexOAuth()
            result = oauth.exchange_code_for_token('test-code')
            assert 'access_token' in result
            assert result['access_token'] == 'dev-token-test-code'
