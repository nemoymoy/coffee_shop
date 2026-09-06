"""Tests for YooKassa (ЮКасса) payment gateway integration."""
import pytest
from decimal import Decimal
from unittest.mock import patch, MagicMock
from coffee_shop.apps.orders.services.yookassa_service import YooKassaService


class TestYooKassaService:
    """Тесты платёжного сервиса ЮКасса."""

    @pytest.fixture(autouse=True)
    def _mock_settings(self, settings):
        """Сбрасываем настройки — ключи пустые для тестов mock-режима."""
        settings.YOOKASSA_SHOP_ID = ''
        settings.YOOKASSA_SECRET_KEY = ''
        settings.YOOKASSA_TEST_MODE = True
        settings.YOOKASSA_WEBHOOK_SECRET = ''
        settings.YOOKASSA_RETURN_URL = ''
        settings.SITE_URL = 'http://localhost:8000'

    def test_is_not_configured(self):
        service = YooKassaService()
        # При пустых ключах — не настроен
        assert service.is_configured() is False

    def test_create_payment_mock_mode(self):
        service = YooKassaService()
        result = service.create_payment(
            order_number='ORD-20260101-000001',
            amount=Decimal('1500'),
            description='Заказ #ORD-20260101-000001',
        )
        # Mock-режим: должна вернуть фейковую ссылку
        assert result['success'] is True
        assert result['mock'] is True
        assert 'confirmation_url' in result
        assert result['amount'] == '1500'

    def test_process_webhook_empty_payload(self):
        service = YooKassaService()
        result = service.process_webhook({})
        assert result['status'] == 'unknown'

    @patch('coffee_shop.apps.orders.services.yookassa_service.WebhookNotificationFactory')
    def test_process_webhook_payment_succeeded(self, mock_factory):
        """Тест обработки события payment.succeeded."""
        # Мокаем объект уведомления
        mock_payment_obj = MagicMock()
        mock_payment_obj.id = 'pay-123'
        mock_payment_obj.metadata = {'order_number': 'ORD-20260101-000001'}
        mock_payment_obj.amount.value = '1500.00'
        mock_payment_obj.paid = True

        mock_notification = MagicMock()
        mock_notification.event = 'payment.succeeded'
        mock_notification.object = mock_payment_obj

        mock_factory.return_value.create.return_value = mock_notification

        service = YooKassaService()
        result = service.process_webhook({
            'type': 'notification',
            'event': 'payment.succeeded',
            'object': {
                'id': 'pay-123',
                'metadata': {'order_number': 'ORD-20260101-000001'},
                'amount': {'value': '1500.00'},
                'paid': True,
            }
        })

        assert result['status'] == 'paid'
        assert result['payment_id'] == 'pay-123'
        assert result['order_number'] == 'ORD-20260101-000001'
        assert result['amount'] == '1500.00'

    @patch('coffee_shop.apps.orders.services.yookassa_service.WebhookNotificationFactory')
    def test_process_webhook_payment_canceled(self, mock_factory):
        """Тест обработки события payment.canceled."""
        # Мокаем объект уведомления
        mock_payment_obj = MagicMock()
        mock_payment_obj.id = 'pay-456'
        mock_payment_obj.metadata = {'order_number': 'ORD-20260101-000002'}
        mock_payment_obj.amount.value = '2000.00'
        mock_payment_obj.paid = False

        mock_notification = MagicMock()
        mock_notification.event = 'payment.canceled'
        mock_notification.object = mock_payment_obj

        mock_factory.return_value.create.return_value = mock_notification

        service = YooKassaService()
        result = service.process_webhook({
            'type': 'notification',
            'event': 'payment.canceled',
            'object': {
                'id': 'pay-456',
                'metadata': {'order_number': 'ORD-20260101-000002'},
                'amount': {'value': '2000.00'},
                'paid': False,
            }
        })

        assert result['status'] == 'failed'
        assert result['payment_id'] == 'pay-456'
        assert result['order_number'] == 'ORD-20260101-000002'

    @patch('coffee_shop.apps.orders.services.yookassa_service.Payment')
    def test_get_payment_status_mock_mode(self, mock_payment):
        """Тест получения статуса платежа в mock-режиме."""
        service = YooKassaService()
        result = service.get_payment_status('pay-test-123')

        assert result['success'] is True
        assert result['mock'] is True
        assert result['status'] == 'confirmed'
        assert result['paid'] is True

    @patch('coffee_shop.apps.orders.services.yookassa_service.Refund')
    def test_refund_payment_mock_mode(self, mock_refund):
        """Тест создания возврата в mock-режиме."""
        service = YooKassaService()
        result = service.refund_payment('pay-123')

        assert result['success'] is True
        assert result['mock'] is True
        assert 'refund_id' in result

    @patch('coffee_shop.apps.orders.services.yookassa_service.SecurityHelper')
    def test_verify_webhook_trusted_ip(self, mock_security_helper):
        """Тест проверки IP доверенного webhook."""
        mock_instance = MagicMock()
        mock_instance.is_notification_trusted.return_value = True
        mock_security_helper.return_value = mock_instance

        service = YooKassaService()
        # Мокаем получение IP
        with patch.object(service, '_get_client_ip', return_value='93.158.136.205'):
            result = service.verify_webhook('test body', 'test signature')
            assert result is True

    @patch('coffee_shop.apps.orders.services.yookassa_service.SecurityHelper')
    def test_verify_webhook_untrusted_ip(self, mock_security_helper):
        """Тест проверки IP недоверенного webhook."""
        mock_instance = MagicMock()
        mock_instance.is_notification_trusted.return_value = False
        mock_security_helper.return_value = mock_instance

        service = YooKassaService()
        with patch.object(service, '_get_client_ip', return_value='1.2.3.4'):
            result = service.verify_webhook('test body', 'test signature')
            assert result is False

    def test_verify_webhook_mock_mode(self):
        """Тест проверки webhook в mock-режиме (всегда True)."""
        service = YooKassaService()
        # При пустых ключах — всегда пропускаем
        assert service.verify_webhook('any body', 'any signature') is True

    @patch('coffee_shop.apps.orders.services.yookassa_service.Payment')
    def test_create_payment_with_credentials(self, mock_payment):
        """Тест создания платежа когда сервис настроен."""
        # Настраиваем сервис
        from django.conf import settings
        settings.YOOKASSA_SHOP_ID = 'test-shop-id'
        settings.YOOKASSA_SECRET_KEY = 'test-secret-key'

        # Мокаем ответ от ЮКасса
        mock_payment_instance = MagicMock()
        mock_payment_instance.id = 'pay-real-123'
        mock_payment_instance.amount.value = '999.00'
        mock_payment_instance.confirmation.confirmation_url = 'https://pay.yookassa.ru/r/test'
        mock_payment.create.return_value = mock_payment_instance

        service = YooKassaService()
        assert service.is_configured() is True

        result = service.create_payment(
            order_number='ORD-20260101-000003',
            amount=Decimal('999'),
            description='Тестовый заказ',
        )

        assert result['success'] is True
        assert result['payment_id'] == 'pay-real-123'
        assert result['confirmation_url'] == 'https://pay.yookassa.ru/r/test'
        assert result['amount'] == '999.00'

        # Проверяем, что Payment.create был вызван с правильными параметрами
        mock_payment.create.assert_called_once()
        call_kwargs = mock_payment.create.call_args[0][0]
        assert call_kwargs['metadata']['order_number'] == 'ORD-20260101-000003'
        assert call_kwargs['amount']['value'] == '999'
        assert call_kwargs['amount']['currency'] == 'RUB'
        assert call_kwargs['capture'] is True

    @patch('coffee_shop.apps.orders.services.yookassa_service.Payment')
    def test_get_payment_status_with_credentials(self, mock_payment):
        """Тест получения статуса платежа когда сервис настроен."""
        from django.conf import settings
        settings.YOOKASSA_SHOP_ID = 'test-shop-id'
        settings.YOOKASSA_SECRET_KEY = 'test-secret-key'

        mock_payment_instance = MagicMock()
        mock_payment_instance.status = 'confirmed'
        mock_payment_instance.amount.value = '1500.00'
        mock_payment_instance.paid = True
        mock_payment_instance.metadata = {'order_number': 'ORD-20260101-000001'}
        mock_payment.find_one.return_value = mock_payment_instance

        service = YooKassaService()
        result = service.get_payment_status('pay-123')

        assert result['success'] is True
        assert result['status'] == 'confirmed'
        assert result['paid'] is True
        assert result['amount'] == '1500.00'
        assert result['metadata']['order_number'] == 'ORD-20260101-000001'

    @patch('coffee_shop.apps.orders.services.yookassa_service.Refund')
    def test_refund_payment_with_credentials(self, mock_refund):
        """Тест создания возврата когда сервис настроен."""
        from django.conf import settings
        settings.YOOKASSA_SHOP_ID = 'test-shop-id'
        settings.YOOKASSA_SECRET_KEY = 'test-secret-key'

        mock_refund_instance = MagicMock()
        mock_refund_instance.id = 'refund-123'
        mock_refund_instance.amount.value = '500.00'
        mock_refund.create.return_value = mock_refund_instance

        service = YooKassaService()
        result = service.refund_payment('pay-123')

        assert result['success'] is True
        assert result['refund_id'] == 'refund-123'
        assert result['amount'] == '500.00'

    @patch('coffee_shop.apps.orders.services.yookassa_service.Refund')
    def test_refund_payment_partial(self, mock_refund):
        """Тест частичного возврата."""
        from django.conf import settings
        settings.YOOKASSA_SHOP_ID = 'test-shop-id'
        settings.YOOKASSA_SECRET_KEY = 'test-secret-key'

        mock_refund_instance = MagicMock()
        mock_refund_instance.id = 'refund-partial-123'
        mock_refund_instance.amount.value = '250.00'
        mock_refund.create.return_value = mock_refund_instance

        service = YooKassaService()
        result = service.refund_payment(
            payment_id='pay-123',
            amount=Decimal('250'),
        )

        assert result['success'] is True
        assert result['refund_id'] == 'refund-partial-123'

        # Проверяем, что был передан partial amount
        call_kwargs = mock_refund.create.call_args[0][0]
        assert call_kwargs['amount']['value'] == '250'
        assert call_kwargs['payment_id'] == 'pay-123'
