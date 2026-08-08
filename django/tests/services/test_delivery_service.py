"""Tests for YandexDeliveryService."""
import pytest
from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService


pytestmark = pytest.mark.django_db


class TestYandexDeliveryService:
    """Тесты сервиса Яндекс Доставки."""

    def test_is_not_configured(self):
        # Без токена и account_id — не настроен
        service = YandexDeliveryService(access_token=None)
        assert service.is_configured() is False

    def test_calculate_price_mock(self):
        # Mock-mode должен работать без настроек
        service = YandexDeliveryService(access_token=None)
        result = service.calculate_price({
            'city': 'moscow',
            'street': 'ул. Тестовая',
            'house': '1',
        })
        assert result['success'] is True
        assert result['mock'] is True
        assert result['price'] == 299
        assert result['eta'] == '30-45 мин'

    def test_create_delivery_order_mock(self):
        service = YandexDeliveryService(access_token=None)
        result = service.create_delivery_order(
            order_id=42,
            address={
                'street': 'ул. Тестовая',
                'house': '1',
                'apartment': '10',
            },
        )
        assert result['success'] is True
        assert result['mock'] is True
        assert result['tracking_number'] == 'YA-DEV-42'

    def test_get_delivery_status_mock(self):
        service = YandexDeliveryService(access_token=None)
        result = service.get_delivery_status('TEST-TRACK')
        assert result['success'] is True
        assert result['mock'] is True
