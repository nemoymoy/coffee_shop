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
        # Вес = вес товара (0.25 кг) + вес тары (0.050 кг)
        assert items[0]['weight'] == pytest.approx(0.30, abs=0.001)
        assert items[0]['size'] == {
            'length': 0.20,
            'width': 0.12,
            'height': 0.12,
        }

    def test_get_origin_point_pickup_uses_pvz(self, settings):
        # Test that pickup delivery type uses PVZ coordinates
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        settings.YANDEX_PVZ_ID = 'd0222b1e-73ff-4274-9c68-42c79d4c7eae'
        settings.YANDEX_PVZ_LAT = 53.200850
        settings.YANDEX_PVZ_LON = 50.150500
        settings.YANDEX_PVZ_ADDRESS = 'г. Самара, ул. Лукачева, д. 6'

        service = YandexDeliveryService()
        origin_lon, origin_lat, origin_address = service._get_origin_point('pickup')

        assert origin_lat == 53.200850
        assert origin_lon == 50.150500
        assert origin_address == 'г. Самара, ул. Лукачева, д. 6'

    def test_get_origin_point_courier_uses_shop(self, settings):
        # Test that courier delivery type uses shop coordinates
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        settings.YANDEX_SHOP_LAT = 53.216940239129094
        settings.YANDEX_SHOP_LON = 50.162688008923745
        settings.YANDEX_SHOP_ADDRESS = 'Самара, ул. Революционная, д. 3'

        service = YandexDeliveryService()
        origin_lon, origin_lat, origin_address = service._get_origin_point('courier')

        assert origin_lat == 53.216940239129094
        assert origin_lon == 50.162688008923745
        assert origin_address == 'Самара, ул. Революционная, д. 3'

    def test_calculate_price_pickup_uses_pvz_origin(self, settings):
        # Test that pickup delivery type sends PVZ coordinates as origin
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        settings.YANDEX_PVZ_ID = 'd0222b1e-73ff-4274-9c68-42c79d4c7eae'
        settings.YANDEX_PVZ_LAT = 53.200850
        settings.YANDEX_PVZ_LON = 50.150500
        settings.YANDEX_PVZ_ADDRESS = 'г. Самара, ул. Лукачева, д. 6'

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
                destination_address='Delivery address',
                delivery_type='pickup',
            )

        assert result['success'] is True
        # Verify the payload sent to the API
        call_args = service.session.post.call_args
        payload = call_args.kwargs['json']
        route_points = payload['route_points']
        # First route point (origin) should be PVZ coordinates
        assert route_points[0]['coordinates'] == [50.150500, 53.200850]
        assert route_points[0]['fullname'] == 'г. Самара, ул. Лукачева, д. 6'
        # Second route point (destination) should be the destination
        assert route_points[1]['coordinates'] == [49.35, 53.21]

    def test_create_order_pickup_uses_pvz_origin_and_pvz_id(self, settings):
        # Test that pickup delivery type uses PVZ as origin and includes pvz_id
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        settings.YANDEX_PVZ_ID = 'd0222b1e-73ff-4274-9c68-42c79d4c7eae'
        settings.YANDEX_PVZ_LAT = 53.200850
        settings.YANDEX_PVZ_LON = 50.150500
        settings.YANDEX_PVZ_ADDRESS = 'г. Самара, ул. Лукачева, д. 6'

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'id': 'cargo-order-pvz',
            'tracking_number': 'YA-TRACK-PVZ',
        }
        mock_response.status_code = 200

        with patch.object(YandexDeliveryService, 'is_configured', return_value=True):
            service = YandexDeliveryService()
            service.session.post = MagicMock(return_value=mock_response)
            result = service.create_order(
                items=[{'quantity': 1, 'weight': 0.5, 'size': {'length': 0.3, 'width': 0.2, 'height': 0.1}, 'title': 'Coffee'}],
                client_order_id='shop-order-pvz',
                destination_coords=[49.35, 53.21],
                destination_address='PVZ address',
                delivery_type='pickup',
                pvz_id='d0222b1e-73ff-4274-9c68-42c79d4c7eae',
            )

        assert result['success'] is True
        # Verify the payload sent to the API
        call_args = service.session.post.call_args
        payload = call_args.kwargs['json']
        route_points = payload['route_points']
        # First route point (origin) should be PVZ coordinates
        assert route_points[0]['coordinates'] == [50.150500, 53.200850]
        assert route_points[0]['address'] == 'г. Самара, ул. Лукачева, д. 6'
        # Second route point (dropoff) should include pvz_id
        assert route_points[1]['type'] == 'dropoff'
        assert route_points[1]['pvz_id'] == 'd0222b1e-73ff-4274-9c68-42c79d4c7eae'

    def test_create_order_courier_uses_shop_origin(self, settings):
        # Test that courier delivery type uses shop coordinates as origin
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        settings.YANDEX_SHOP_LAT = 53.216940239129094
        settings.YANDEX_SHOP_LON = 50.162688008923745
        settings.YANDEX_SHOP_ADDRESS = 'Самара, ул. Революционная, д. 3'

        mock_response = MagicMock()
        mock_response.json.return_value = {
            'id': 'cargo-order-courier',
            'tracking_number': 'YA-TRACK-COURIER',
        }
        mock_response.status_code = 200

        with patch.object(YandexDeliveryService, 'is_configured', return_value=True):
            service = YandexDeliveryService()
            service.session.post = MagicMock(return_value=mock_response)
            result = service.create_order(
                items=[{'quantity': 1, 'weight': 0.5, 'size': {'length': 0.3, 'width': 0.2, 'height': 0.1}, 'title': 'Coffee'}],
                client_order_id='shop-order-courier',
                destination_coords=[49.35, 53.21],
                destination_address='Delivery address',
                delivery_type='courier',
            )

        assert result['success'] is True
        # Verify the payload sent to the API
        call_args = service.session.post.call_args
        payload = call_args.kwargs['json']
        route_points = payload['route_points']
        # First route point (origin) should be shop coordinates
        assert route_points[0]['coordinates'] == [50.162688008923745, 53.216940239129094]
        assert route_points[0]['address'] == 'Самара, ул. Революционная, д. 3'
        # Second route point (dropoff) should be the delivery address
        assert route_points[1]['type'] == 'dropoff'
        assert route_points[1]['address'] == 'Delivery address'

    def test_pvz_config_defaults(self, settings):
        # Test that PVZ config has correct default values
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        # Remove custom PVZ settings to test defaults
        if hasattr(settings, 'YANDEX_PVZ_ID'):
            delattr(settings, 'YANDEX_PVZ_ID')
        if hasattr(settings, 'YANDEX_PVZ_LAT'):
            delattr(settings, 'YANDEX_PVZ_LAT')
        if hasattr(settings, 'YANDEX_PVZ_LON'):
            delattr(settings, 'YANDEX_PVZ_LON')
        if hasattr(settings, 'YANDEX_PVZ_ADDRESS'):
            delattr(settings, 'YANDEX_PVZ_ADDRESS')

        service = YandexDeliveryService()
        assert service.pvz_id == 'd0222b1e-73ff-4274-9c68-42c79d4c7eae'
        assert service.pvz_lat == 53.200850
        assert service.pvz_lon == 50.150500
        assert service.pvz_address == 'г. Самара, ул. Лукачева, д. 6'

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
        # weight_grams=0, Package.for_weight(0) returns 'light' (tare=0.023kg)
        # weight_kg=0.0 + tare=0.023 = 0.023
        assert items[0]['weight'] == pytest.approx(0.023, abs=0.001)
        assert items[0]['size']['length'] == pytest.approx(0.12, abs=0.001)


class TestRateLimiting:
    """Tests for rate limiting decorators."""

    def test_rate_limited_decorator_exists(self):
        # Verify decorator is importable
        from coffee_shop.apps.orders.services.delivery_service import rate_limited
        assert callable(rate_limited)
