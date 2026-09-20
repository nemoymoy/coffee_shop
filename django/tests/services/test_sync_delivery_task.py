"""Tests for Yandex Delivery sync task (Cargo API)."""
import pytest
from unittest.mock import patch, MagicMock
from decimal import Decimal

from coffee_shop.apps.orders.models import Order
from coffee_shop.tasks import sync_yandex_delivery_status

pytestmark = pytest.mark.django_db


class TestSyncYandexDeliveryStatus:
    """Tests for Cargo API delivery status sync."""

    def test_sync_no_matching_orders(self):
        """No orders to sync."""
        result = sync_yandex_delivery_status()
        assert 'Synced 0 of 0' in result

    def test_sync_express_orders(self, user):
        """Express orders are synced via get_express_claim_info."""
        order = Order.objects.create(
            user=user,
            status=Order.Status.PAID,
            total_amount=Decimal('1000'),
            payment_method=Order.PaymentMethod.ONLINE,
            delivery_method=Order.DeliveryMethod.DELIVERY,
            delivery_api_type='express',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            express_claim_id='CLAIM-123',
        )

        with patch(
            'coffee_shop.apps.orders.services.delivery_service.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_express_claim_info.return_value = {
                'success': True,
                'status': 'accepted',
            }
            MockService.return_value = mock_instance

            result = sync_yandex_delivery_status()

        assert 'Synced 1 of 1' in result
        order.refresh_from_db()
        assert order.delivery_status == 'accepted'

    def test_sync_other_day_orders(self, user):
        """Other Day orders are synced via get_request_info."""
        order = Order.objects.create(
            user=user,
            status=Order.Status.PAID,
            total_amount=Decimal('1000'),
            payment_method=Order.PaymentMethod.ONLINE,
            delivery_method=Order.DeliveryMethod.DELIVERY,
            delivery_api_type='other_day',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            yandex_order_id='REQ-456',
        )

        with patch(
            'coffee_shop.apps.orders.services.delivery_service.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_request_info.return_value = {
                'success': True,
                'status': 'in_transit',
            }
            MockService.return_value = mock_instance

            result = sync_yandex_delivery_status()

        assert 'Synced 1 of 1' in result
        order.refresh_from_db()
        assert order.delivery_status == 'in_transit'

    def test_sync_delivered_status_updates_order(self, user):
        """Delivered status from Express updates Order status."""
        order = Order.objects.create(
            user=user,
            status=Order.Status.PAID,
            total_amount=Decimal('1000'),
            payment_method=Order.PaymentMethod.ONLINE,
            delivery_method=Order.DeliveryMethod.DELIVERY,
            delivery_api_type='express',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            express_claim_id='CLAIM-789',
        )

        with patch(
            'coffee_shop.apps.orders.services.delivery_service.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_express_claim_info.return_value = {
                'success': True,
                'status': 'delivered',
            }
            MockService.return_value = mock_instance

            sync_yandex_delivery_status()

        order.refresh_from_db()
        assert order.delivery_status == 'delivered'
        assert order.status == Order.Status.DELIVERED

    def test_sync_service_error_ignored(self, user):
        """Service error — order is not updated."""
        order = Order.objects.create(
            user=user,
            status=Order.Status.PAID,
            total_amount=Decimal('1000'),
            payment_method=Order.PaymentMethod.ONLINE,
            delivery_method=Order.DeliveryMethod.DELIVERY,
            delivery_api_type='express',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            express_claim_id='CLAIM-ERR',
        )

        with patch(
            'coffee_shop.apps.orders.services.delivery_service.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_express_claim_info.return_value = {
                'success': False,
                'error': 'Rate limited',
            }
            MockService.return_value = mock_instance

            result = sync_yandex_delivery_status()

        assert 'Synced 0 of 1' in result
        order.refresh_from_db()
        assert order.delivery_status is None

    def test_sync_ignores_non_matching_statuses(self, user):
        """Orders with NEW/PAID status are not synced."""
        Order.objects.create(
            user=user,
            status=Order.Status.NEW,
            total_amount=Decimal('1000'),
            payment_method=Order.PaymentMethod.ONLINE,
            delivery_method=Order.DeliveryMethod.DELIVERY,
            delivery_api_type='express',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            express_claim_id='CLAIM-IGNORE',
        )

        with patch(
            'coffee_shop.apps.orders.services.delivery_service.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            MockService.return_value = mock_instance

            result = sync_yandex_delivery_status()

        assert 'Synced 0 of 0' in result
        mock_instance.get_express_claim_info.assert_not_called()
