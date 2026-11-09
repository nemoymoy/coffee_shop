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
        assert order.yandex_delivery_status_raw == 'accepted'
        assert order.yandex_delivery_status == 'accepted'

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
            # 'in_work' is in OTHER_DAY_IN_PROGRESS_STATUSES
            mock_instance.get_request_info.return_value = {
                'success': True,
                'status': 'in_work',
            }
            MockService.return_value = mock_instance

            result = sync_yandex_delivery_status()

        assert 'Synced 1 of 1' in result
        order.refresh_from_db()
        assert order.yandex_delivery_status_raw == 'in_work'
        assert order.yandex_delivery_status == 'in_work'

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
        assert order.yandex_delivery_status_raw == 'delivered'
        assert order.yandex_delivery_status == 'delivered'
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
        assert order.yandex_delivery_status_raw is None

    def test_sync_cancellation_for_new_order(self, user):
        """Cancelled Express claim updates order status from 'new' to 'cancelled'.

        Regression test: orders with status 'new' or 'awaiting_payment'
        must be synced so we catch cancellations from Yandex Delivery.
        """
        order = Order.objects.create(
            user=user,
            status=Order.Status.NEW,
            total_amount=Decimal('1000'),
            payment_method=Order.PaymentMethod.CASH,
            delivery_method=Order.DeliveryMethod.DELIVERY,
            delivery_api_type='express',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            express_claim_id='CLAIM-CANCELLED',
        )

        with patch(
            'coffee_shop.apps.orders.services.delivery_service.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_express_claim_info.return_value = {
                'success': True,
                'status': 'cancelled',
            }
            MockService.return_value = mock_instance

            result = sync_yandex_delivery_status()

        assert 'Synced 1 of 1' in result
        order.refresh_from_db()
        assert order.status == Order.Status.CANCELED
        assert order.yandex_delivery_status_raw == 'cancelled'
        assert order.yandex_delivery_status == 'cancelled'

    def test_sync_cancellation_for_awaiting_payment_order(self, user):
        """Cancelled Express claim updates order from 'awaiting_payment' to 'cancelled'."""
        order = Order.objects.create(
            user=user,
            status=Order.Status.AWAITING_PAYMENT,
            total_amount=Decimal('1000'),
            payment_method=Order.PaymentMethod.ONLINE,
            delivery_method=Order.DeliveryMethod.DELIVERY,
            delivery_api_type='express',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            express_claim_id='CLAIM-CANCELLED-2',
        )

        with patch(
            'coffee_shop.apps.orders.services.delivery_service.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_express_claim_info.return_value = {
                'success': True,
                'status': 'cancelled',
            }
            MockService.return_value = mock_instance

            sync_yandex_delivery_status()

        order.refresh_from_db()
        assert order.status == Order.Status.CANCELED
        assert order.yandex_delivery_status_raw == 'cancelled'
        assert order.yandex_delivery_status == 'cancelled'

    def test_sync_includes_all_statuses(self, user):
        """Orders with any status are synced if they have express_claim_id."""
        order = Order.objects.create(
            user=user,
            status=Order.Status.NEW,
            total_amount=Decimal('1000'),
            payment_method=Order.PaymentMethod.CASH,
            delivery_method=Order.DeliveryMethod.DELIVERY,
            delivery_api_type='express',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            express_claim_id='CLAIM-ANY-STATUS',
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
        mock_instance.get_express_claim_info.assert_called_once_with('CLAIM-ANY-STATUS')
