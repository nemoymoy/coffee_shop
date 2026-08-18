"""Tests for Yandex Delivery sync task."""
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from coffee_shop.apps.orders.models import Order
from coffee_shop.tasks import sync_yandex_delivery_status

pytestmark = pytest.mark.django_db


class TestSyncYandexDeliveryStatus:
    """Тесты синхронизации статусов Яндекс Доставки."""

    def test_sync_no_matching_orders(self):
        """Нет заказов для синхронизации."""
        result = sync_yandex_delivery_status()
        assert 'Synced 0 of 0' in result

    def test_sync_orders_without_token(self, user):
        """Заказы без токена пропускаются."""
        Order.objects.create(
            user=user,
            status='in_progress',
            total_amount=Decimal('1000'),
            payment_method='online',
            delivery_method='delivery',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            yandex_order_id='YDO-123',
            tracking_number='YA-TRACK-001',
        )

        result = sync_yandex_delivery_status()
        # Orders without token are filtered out, so 0 of 0
        assert 'Synced 0 of 0' in result

    def test_sync_updates_status(self, user):
        """Статусы заказов обновляются."""
        order = Order.objects.create(
            user=user,
            status='in_progress',
            total_amount=Decimal('1000'),
            payment_method='online',
            delivery_method='delivery',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            yandex_order_id='YDO-123',
            tracking_number='YA-TRACK-001',
            yandex_access_token='ya2-test-token',
        )

        with patch(
            'coffee_shop.apps.orders.services.delivery_service.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_delivery_status.return_value = {
                'success': True,
                'status': 'in_transit',
                'history': [],
            }
            MockService.return_value = mock_instance

            result = sync_yandex_delivery_status()

        assert 'Synced 1 of 1' in result
        order.refresh_from_db()
        assert order.delivery_status == 'in_transit'
        # Status should remain 'in_progress'
        assert order.status == 'in_progress'

    def test_sync_delivered_status(self, user):
        """Статус 'delivered' обновляет Order."""
        order = Order.objects.create(
            user=user,
            status='in_progress',
            total_amount=Decimal('1000'),
            payment_method='online',
            delivery_method='delivery',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            yandex_order_id='YDO-123',
            tracking_number='YA-TRACK-001',
            yandex_access_token='ya2-test-token',
        )

        with patch(
            'coffee_shop.apps.orders.services.delivery_service.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_delivery_status.return_value = {
                'success': True,
                'status': 'delivered',
            }
            MockService.return_value = mock_instance

            sync_yandex_delivery_status()

        order.refresh_from_db()
        assert order.delivery_status == 'delivered'
        assert order.status == 'delivered'

    def test_sync_service_error(self, user):
        """Ошибка сервиса — заказ не обновляется."""
        Order.objects.create(
            user=user,
            status='in_progress',
            total_amount=Decimal('1000'),
            payment_method='online',
            delivery_method='delivery',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            yandex_order_id='YDO-123',
            tracking_number='YA-TRACK-001',
            yandex_access_token='ya2-test-token',
        )

        with patch(
            'coffee_shop.apps.orders.services.delivery_service.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_delivery_status.return_value = {
                'success': False,
                'error': 'Rate limited',
            }
            MockService.return_value = mock_instance

            result = sync_yandex_delivery_status()

        assert 'Synced 0 of 1' in result
