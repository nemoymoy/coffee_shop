"""Tests for YooMoney (ЮКасса) payment gateway."""
import pytest
from decimal import Decimal
from coffee_shop.apps.orders.services.payment_service import YooMoneyService


class TestYooMoneyService:
    """Тесты платёжного сервиса ЮКасса."""

    @pytest.fixture(autouse=True)
    def _mock_settings(self, settings):
        """Сбрасываем настройки — ключи пустые для тестов mock-режима."""
        settings.YOOKASSA_MERCHANT_ID = ''
        settings.YOOKASSA_API_KEY = ''
        settings.YOOKASSA_TEST_MODE = True
        settings.YOOKASSA_WEBHOOK_SECRET = ''
        settings.YOOKASSA_RETURN_URL = ''

    def test_is_not_configured(self):
        service = YooMoneyService()
        # При пустых ключах — не настроен
        assert service.is_configured() is False

    def test_create_payment_link_no_credentials(self):
        service = YooMoneyService()
        result = service.create_payment_link(
            order_id=1,
            amount=Decimal('1500'),
            description='Заказ #1',
        )
        # Mock-режим: должна вернуть фейковую ссылку
        assert result['success'] is True
        assert result['mock'] is True
        assert 'payment_url' in result

    def test_handle_webhook_empty_payload(self):
        service = YooMoneyService()
        result = service.handle_webhook({})
        assert result['status'] == 'unknown'
