"""Tests for YandexDeliveryService (Other Day API)."""
import pytest
from unittest.mock import patch, MagicMock
from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService
from coffee_shop.apps.orders.models import Order, OrderItem, Package


pytestmark = pytest.mark.django_db


class TestYandexDeliveryService:
    """Tests for Yandex Delivery Service."""

    def test_is_not_configured_no_token(self, settings):
        # Without token — not configured
        settings.YANDEX_DELIVERY_TOKEN = ''
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

    def test_get_offers_info_not_configured(self):
        # Not configured — should return error without making API call
        with patch.object(YandexDeliveryService, 'is_configured', return_value=False):
            service = YandexDeliveryService()
            result = service.get_offers_info(
                items_data=[],
                places_data=[],
                client_order_id='test-123',
                destination_coords=[49.35, 53.21],
                destination_address='Test address',
                delivery_type='courier',
            )
            assert result['success'] is False
            assert 'not configured' in result['error'].lower() or 'не настроена' in result['error'].lower()

    def test_get_request_info_not_configured(self):
        # Not configured — should return error
        with patch.object(YandexDeliveryService, 'is_configured', return_value=False):
            service = YandexDeliveryService()
            result = service.get_request_info('request-123')
            assert result['success'] is False

    def test_get_offers_info_success(self, settings):
        # Test offers/info with mocked session
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'offers': [
                {
                    'offer_id': 'offer-123',
                    'delivery_interval': {'from': '2026-09-15T10:00:00Z', 'to': '2026-09-15T14:00:00Z'},
                }
            ],
        }
        mock_response.status_code = 200

        with patch.object(YandexDeliveryService, 'is_configured', return_value=True):
            service = YandexDeliveryService()
            service.session.post = MagicMock(return_value=mock_response)
            result = service.get_offers_info(
                items_data=[{'count': 1, 'name': 'Coffee'}],
                places_data=[{'barcode': 'BOX-001'}],
                client_order_id='test-123',
                destination_coords=[49.35, 53.21],
                destination_address='Test address',
                delivery_type='courier',
            )

        assert result['success'] is True
        assert len(result['offers']) == 1
        assert result['offers'][0]['offer_id'] == 'offer-123'

    def test_get_request_info_success(self, settings):
        # Test status retrieval
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        mock_response = MagicMock()
        mock_response.json.return_value = {
            'status': 'in_work',
            'tracking_number': 'YA-TRACK-001',
        }
        mock_response.status_code = 200

        with patch.object(YandexDeliveryService, 'is_configured', return_value=True):
            service = YandexDeliveryService()
            service.session.get = MagicMock(return_value=mock_response)
            result = service.get_request_info('request-123')

        assert result['success'] is True
        assert result['status'] == 'in_work'
        assert result['tracking_number'] == 'YA-TRACK-001'

    def test_build_items_payload_for_other_day_with_package(self, coffee_beans, user):
        # Test building items and places from OrderItem with package
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
        items, places = service._build_items_payload_for_other_day([order_item])

        assert len(items) == 1
        assert items[0]['count'] == order_item.quantity
        assert items[0]['name'] == order_item.product.name
        # Вес = вес товара (0.25 кг) + вес тары (0.050 кг)
        assert items[0]['weight'] == pytest.approx(0.30, abs=0.001)
        assert items[0]['physical_dims'] == {
            'dx': 20,  # cm (0.20m * 100)
            'dy': 12,  # cm (0.12m * 100)
            'dz': 12,  # cm (0.12m * 100)
        }
        # Places should have weight_gross
        assert len(places) == 1
        assert places[0]['physical_dims']['weight_gross'] == 250 + 50  # 250g product + 50g tare

    def test_build_items_payload_for_other_day_without_package(self, coffee_beans, user):
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
        items, places = service._build_items_payload_for_other_day([order_item])

        assert len(items) == 1
        # weight_grams=0, Package.for_weight(0) returns 'light' (tare=0.023kg)
        # weight_kg=0.0 + tare=0.023 = 0.023
        assert items[0]['weight'] == pytest.approx(0.023, abs=0.001)
        assert items[0]['physical_dims']['dx'] == pytest.approx(12, abs=1)  # cm

    def test_build_source_destination_pickup_uses_pickup_station(self, settings):
        # Test that pickup delivery type uses pickup_station_id as source
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        settings.YANDEX_PICKUP_STATION_ID = 'pickup-station-123'

        service = YandexDeliveryService()
        source, destination, policy = service._build_source_destination('pickup', pvz_id='pvz-user-selected')

        assert source == {'platform_station_id': 'pickup-station-123'}
        assert destination == {
            'type': 'platform_station',
            'platform_station_id': 'pvz-user-selected',
        }
        assert policy == 'self_pickup'

    def test_build_source_destination_pickup_fallback_to_pickup_station(self, settings):
        # Test that pickup uses pickup_station_id as fallback when pvz_id not provided
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        settings.YANDEX_PICKUP_STATION_ID = 'pickup-station-123'

        service = YandexDeliveryService()
        source, destination, policy = service._build_source_destination('pickup', pvz_id=None)

        assert source == {'platform_station_id': 'pickup-station-123'}
        assert destination == {
            'type': 'platform_station',
            'platform_station_id': 'pickup-station-123',
        }

    def test_build_source_destination_courier_uses_warehouse(self):
        # Test that courier delivery type uses test_warehouse_id as source
        from django.conf import settings as django_settings
        from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService

        django_settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        django_settings.YANDEX_DELIVERY_TEST_MODE = True
        django_settings.YANDEX_DELIVERY_TEST_WAREHOUSE_ID = 'warehouse-456'

        # Create fresh service to pick up new settings
        service = YandexDeliveryService()
        source, destination, policy = service._build_source_destination('courier', pvz_id=None)

        assert source == {'platform_station_id': 'warehouse-456'}
        assert destination is None
        assert policy == 'time_interval'

    def test_build_items_for_other_day_preserves_places(self):
        # Test that _build_items_for_other_day preserves separate items and places
        items = [
            {
                'count': 2,
                'name': 'Coffee',
                'weight': 0.3,
                'place_barcode': 'BOX-001',
            }
        ]
        places = [
            {
                'barcode': 'BOX-001',
                'physical_dims': {'weight_gross': 350},
            }
        ]

        service = YandexDeliveryService()
        result_items, result_places = service._build_items_for_other_day(
            items, places, 'pickup', None
        )

        assert len(result_items) == 1
        assert len(result_places) == 1
        # Items should have billing_details added
        assert 'billing_details' in result_items[0]
        # Places should retain their own structure
        assert result_places[0]['physical_dims']['weight_gross'] == 350
        # Places should NOT have items fields mixed in
        assert 'weight' not in result_places[0]

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
        # pickup_station_id should also be available
        assert service.pickup_station_id == 'd0222b1e-73ff-4274-9c68-42c79d4c7eae'


class TestRateLimiting:
    """Tests for rate limiting decorators."""

    def test_rate_limited_decorator_exists(self):
        # Verify decorator is importable
        from coffee_shop.apps.orders.services.delivery_service import rate_limited
        assert callable(rate_limited)

    def test_retry_with_backoff_decorator_exists(self):
        # Verify decorator is importable
        from coffee_shop.apps.orders.services.delivery_service import retry_with_backoff
        assert callable(retry_with_backoff)
