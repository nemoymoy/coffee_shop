"""Tests for YandexDeliveryService (Cargo API)."""
import pytest
from unittest.mock import patch, MagicMock
from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService
from coffee_shop.apps.orders.models import Order, OrderItem


pytestmark = pytest.mark.django_db


class TestYandexDeliveryService:
    """Tests for Yandex Cargo Delivery Service."""

    def test_is_not_configured_no_token(self):
        # Without token — not configured
        with patch('coffee_shop.apps.orders.services.delivery_service.settings', **{
            'YANDEX_DELIVERY_TOKEN': '',
            'YANDEX_SHOP_LAT': 53.1960,
            'YANDEX_SHOP_LON': 49.3782,
            'YANDEX_SHOP_ADDRESS': 'Test address',
        }):
            service = YandexDeliveryService()
            assert service.is_configured() is False

    def test_is_configured_with_valid_token(self, settings):
        # With valid token — configured
        settings.YANDEX_DELIVERY_TOKEN = 'ya2-test-token'
        service = YandexDeliveryService()
        assert service.is_configured() is True

    def test_is_configured_with_dev_token(self, settings):
        # With dev token — configured
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token-test'
        service = YandexDeliveryService()
        assert service.is_configured() is True

    def test_is_configured_with_invalid_token(self, settings):
        # Invalid token prefix — not configured
        settings.YANDEX_DELIVERY_TOKEN = 'invalid-token'
        service = YandexDeliveryService()
        assert service.is_configured() is False

    @patch.object(YandexDeliveryService, 'is_configured')
    def test_calculate_price_not_configured(self, mock_is_configured):
        # Not configured — should return error without making API call
        mock_is_configured.return_value = False
        service = YandexDeliveryService()
        result = service.calculate_price(
            items=[{'quantity': 1, 'weight': 0.5, 'size': {'length': 0.3, 'width': 0.2, 'height': 0.1}}],
            destination_coords=[49.35, 53.21],
            destination_address='Test address',
            delivery_type='courier',
        )
        assert result['success'] is False
        assert 'not configured' in result['error'].lower() or 'не настроена' in result['error'].lower()

    @patch.object(YandexDeliveryService, 'is_configured')
    def test_get_order_status_not_configured(self, mock_is_configured):
        # Not configured — should return error
        mock_is_configured.return_value = False
        service = YandexDeliveryService()
        result = service.get_order_status('cargo-order-123')
        assert result['success'] is False

    def test_calculate_price_success(self, settings):
        # Test successful price calculation with mocked session
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'price': '350.00',
            'currency_rules': {'currency': 'RUB'},
            'delivery_days': 2,
        }
        mock_response.status_code = 200

        with patch.object(YandexDeliveryService, 'is_configured', return_value=True):
            service = YandexDeliveryService()
            service.session.post = MagicMock(return_value=mock_response)
            result = service.calculate_price(
                items=[{'quantity': 1, 'weight': 0.5, 'size': {'length': 0.3, 'width': 0.2, 'height': 0.1}}],
                destination_coords=[49.35, 53.21],
                destination_address='Test address',
                delivery_type='courier',
            )

        assert result['success'] is True
        assert result['price'] == '350.00'
        assert result['delivery_days'] == 2

    def test_calculate_price_pickup_type(self, settings):
        # Test pickup delivery type
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'price': '250.00',
            'currency_rules': {'currency': 'RUB'},
        }
        mock_response.status_code = 200

        with patch.object(YandexDeliveryService, 'is_configured', return_value=True):
            service = YandexDeliveryService()
            service.session.post = MagicMock(return_value=mock_response)
            result = service.calculate_price(
                items=[{'quantity': 1, 'weight': 0.5, 'size': {'length': 0.3, 'width': 0.2, 'height': 0.1}}],
                destination_coords=[49.35, 53.21],
                destination_address='PVZ address',
                delivery_type='pickup',
            )

        assert result['success'] is True

    def test_create_order_success(self, settings):
        # Test order creation
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'id': 'cargo-order-123',
            'tracking_number': 'YA-TRACK-456',
        }
        mock_response.status_code = 200

        with patch.object(YandexDeliveryService, 'is_configured', return_value=True):
            service = YandexDeliveryService()
            service.session.post = MagicMock(return_value=mock_response)
            result = service.create_order(
                items=[{'quantity': 1, 'weight': 0.5, 'size': {'length': 0.3, 'width': 0.2, 'height': 0.1}, 'title': 'Coffee'}],
                client_order_id='shop-order-789',
                destination_coords=[49.35, 53.21],
                destination_address='Delivery address',
                delivery_type='courier',
            )

        assert result['success'] is True
        assert result['order_id'] == 'cargo-order-123'
        assert result['tracking_number'] == 'YA-TRACK-456'

    def test_create_order_with_pvz_id(self, settings):
        # Test order creation with PVZ ID
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'id': 'cargo-order-456',
            'tracking_number': 'YA-TRACK-789',
        }
        mock_response.status_code = 200

        with patch.object(YandexDeliveryService, 'is_configured', return_value=True):
            service = YandexDeliveryService()
            service.session.post = MagicMock(return_value=mock_response)
            result = service.create_order(
                items=[{'quantity': 1, 'weight': 0.5, 'size': {'length': 0.3, 'width': 0.2, 'height': 0.1}, 'title': 'Coffee'}],
                client_order_id='shop-order-999',
                destination_coords=[49.35, 53.21],
                destination_address='PVZ address',
                delivery_type='pickup',
                pvz_id='pvz-12345',
            )

        assert result['success'] is True

    def test_get_order_status_success(self, settings):
        # Test status retrieval
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'in_transit',
            'tracking_number': 'YA-TRACK-001',
        }
        mock_response.status_code = 200

        with patch.object(YandexDeliveryService, 'is_configured', return_value=True):
            service = YandexDeliveryService()
            service.session.get = MagicMock(return_value=mock_response)
            result = service.get_order_status('cargo-order-123')

        assert result['success'] is True
        assert result['status'] == 'in_transit'
        assert result['tracking_number'] == 'YA-TRACK-001'

    def test_build_items_payload_with_package(self, coffee_beans, user):
        # Test building items payload from OrderItem with package
        from coffee_shop.apps.orders.models import Package
        
        package, created = Package.objects.get_or_create(
            weight_range='medium',
            defaults={
                'length': 0.20,
                'width': 0.12,
                'height': 0.12,
                'tare_weight': 0.050,
            }
        )

        order = Order.objects.create(
            user=user,
            first_name='Test',
            last_name='User',
            phone='+79990000000',
            email='test@test.com',
            delivery_method='pickup',
            payment_method='online',
            total_amount=100,
        )
        order_item = OrderItem.objects.create(
            order=order,
            product=coffee_beans,
            quantity=1,
            unit_price=100,
            package=package,
            weight_grams=250,
        )

        service = YandexDeliveryService()
        items = service.build_items_payload([order_item])

        assert len(items) == 1
        assert items[0]['quantity'] == order_item.quantity
        assert items[0]['title'] == order_item.product.name
        assert items[0]['weight'] == 0.25  # 250g in kg

    def test_build_items_payload_without_package(self, coffee_beans, user):
        # Test building items payload without package
        
        order = Order.objects.create(
            user=user,
            first_name='Test',
            last_name='User',
            phone='+79990000000',
            email='test@test.com',
            delivery_method='pickup',
            payment_method='online',
            total_amount=100,
        )
        order_item = OrderItem.objects.create(
            order=order,
            product=coffee_beans,
            quantity=1,
            unit_price=100,
            package=None,
            weight_grams=0,
        )

        service = YandexDeliveryService()
        items = service.build_items_payload([order_item])

        assert len(items) == 1
        assert items[0]['weight'] == 0.5  # default weight
        assert items[0]['size']['length'] == 0.20  # default size


class TestRateLimiting:
    """Tests for rate limiting decorators."""

    def test_rate_limited_decorator_exists(self):
        # Verify decorator is importable
        from coffee_shop.apps.orders.services.delivery_service import rate_limited
        assert callable(rate_limited)
