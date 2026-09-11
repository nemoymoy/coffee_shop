"""Tests for Other Day API (scheduled delivery)."""
from unittest.mock import MagicMock, patch

import pytest

from coffee_shop.apps.orders.models import Order
from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService


class TestOtherDayDeliveryService:
    """Tests for Other Day API methods."""

    @pytest.fixture
    def service(self, settings):
        settings.YANDEX_DELIVERY_TOKEN = 'ya2_test_token_123'
        settings.YANDEX_EXPRESS_BASE_URL = 'https://b2b.taxi.yandex.net/b2b/cargo/integration/v2'
        settings.YANDEX_SHOP_LAT = 53.2169
        settings.YANDEX_SHOP_LON = 50.1627
        settings.YANDEX_SHOP_ADDRESS = 'Самара, ул. Революционная, д. 3'
        settings.YANDEX_PVZ_ID = 'test-pvz-id'
        settings.YANDEX_PVZ_LAT = 53.2008
        settings.YANDEX_PVZ_LON = 50.1505
        settings.YANDEX_PVZ_ADDRESS = 'г. Самара, ул. Лукачева, д. 6'
        settings.YANDEX_DELIVERY_TEST_MODE = False
        return YandexDeliveryService()

    @pytest.fixture
    def other_day_items(self):
        return [{
            'count': 2,
            'name': 'Кофе 250г',
            'physical_dims': {
                'dx': 120,
                'dy': 60,
                'dz': 60,
            },
        }]

    def test_create_order_courier_success(self, service, other_day_items):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'request_id': 'req-123',
            'tracking_number': 'TRACK-456',
        }

        with patch.object(service.session, 'post', return_value=mock_response):
            result = service.create_order(
                items=other_day_items,
                client_order_id='order-1',
                destination_coords=[37.59, 55.75],
                destination_address='Москва, ул. Арбат, 10',
                delivery_type='courier',
                recipient_name='Иван Петров',
                recipient_phone='+79001234567',
                email='ivan@example.com',
                delivery_cost=350,
                payment_method='already_paid',
            )

        assert result['success'] is True
        assert result['request_id'] == 'req-123'
        assert result['tracking_number'] == 'TRACK-456'

    def test_create_order_pvz_success(self, service, other_day_items):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'request_id': 'req-pvz-123',
        }

        with patch.object(service.session, 'post', return_value=mock_response):
            result = service.create_order(
                items=other_day_items,
                client_order_id='order-2',
                destination_coords=[50.15, 53.20],
                destination_address='Самара, ул. Ленина, 1',
                delivery_type='pickup',
                pvz_id='pvz-target-id',
                recipient_name='Иван Петров',
                recipient_phone='+79001234567',
                email='ivan@example.com',
            )

        assert result['success'] is True
        assert result['request_id'] == 'req-pvz-123'

    def test_get_offers_success(self, service, other_day_items):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'offers': [
                {
                    'offer_id': 'offer-123',
                    'expires_at': '2026-09-12T15:00:00.000000Z',
                    'offer_details': {
                        'pricing_total': '1400.96 RUB',
                        'delivery_interval': {
                            'min': '2026-09-12T09:00:00.000000Z',
                            'max': '2026-09-12T18:00:00.000000Z',
                            'policy': 'time_interval',
                        },
                    },
                }
            ],
        }

        with patch.object(service.session, 'post', return_value=mock_response):
            result = service.get_offers(
                items=other_day_items,
                client_order_id='order-3',
                destination_coords=[37.59, 55.75],
                destination_address='Москва, ул. Арбат, 10',
                delivery_type='courier',
            )

        assert result['success'] is True
        assert len(result['offers']) == 1
        assert result['offers'][0]['offer_id'] == 'offer-123'

    def test_confirm_offer_success(self, service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'request_id': 'req-confirmed-123',
        }

        with patch.object(service.session, 'post', return_value=mock_response):
            result = service.confirm_offer('offer-123')

        assert result['success'] is True
        assert result['request_id'] == 'req-confirmed-123'

    def test_get_request_info_success(self, service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'request_id': 'req-123',
            'status': 'in_work',
            'tracking_number': 'TRACK-456',
        }

        with patch.object(service.session, 'post', return_value=mock_response):
            result = service.get_request_info('req-123')

        assert result['success'] is True
        assert result['status'] == 'in_work'
        assert result['tracking_number'] == 'TRACK-456'

    def test_build_interval_utc(self):
        from datetime import datetime
        from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService

        from_dt = datetime(2026, 9, 12, 9, 0, 0)
        to_dt = datetime(2026, 9, 12, 18, 0, 0)

        result = YandexDeliveryService._build_interval_utc(from_dt, to_dt)

        assert result['from'] == '2026-09-12T09:00:00.000000Z'
        assert result['to'] == '2026-09-12T18:00:00.000000Z'

    def test_build_interval_utc_none(self):
        result = YandexDeliveryService._build_interval_utc(None, None)
        assert result == {}


class TestOtherDayStatusMapping:
    """Tests for Other Day API status mapping."""

    def test_other_day_delivered_statuses(self):
        from coffee_shop.apps.orders.tasks import (
            OTHER_DAY_DELIVERED_STATUSES, _map_yandex_status_to_order
        )
        assert 'delivered_to_address' in OTHER_DAY_DELIVERED_STATUSES
        assert 'delivered_to_point' in OTHER_DAY_DELIVERED_STATUSES
        assert 'finished' in OTHER_DAY_DELIVERED_STATUSES

    def test_other_day_in_progress_statuses(self):
        from coffee_shop.apps.orders.tasks import (
            OTHER_DAY_IN_PROGRESS_STATUSES, _map_yandex_status_to_order
        )
        assert 'created' in OTHER_DAY_IN_PROGRESS_STATUSES
        assert 'in_work' in OTHER_DAY_IN_PROGRESS_STATUSES
        assert 'picked_up' in OTHER_DAY_IN_PROGRESS_STATUSES
        assert 'delivered' in OTHER_DAY_IN_PROGRESS_STATUSES

    def test_map_other_day_finished(self):
        from coffee_shop.apps.orders.tasks import _map_yandex_status_to_order
        order_status, is_final = _map_yandex_status_to_order(
            'finished', api_type='other_day'
        )
        assert order_status == 'delivered'
        assert is_final is True

    def test_map_other_day_in_work(self):
        from coffee_shop.apps.orders.tasks import _map_yandex_status_to_order
        order_status, is_final = _map_yandex_status_to_order(
            'in_work', api_type='other_day'
        )
        assert order_status == 'in_progress'
        assert is_final is False


class TestBuildItemsPayload:
    """Tests for build_items_payload method."""

    @pytest.fixture
    def service(self, settings):
        settings.YANDEX_DELIVERY_TOKEN = 'ya2_test_token_123'
        settings.YANDEX_EXPRESS_BASE_URL = 'https://b2b.taxi.yandex.net/b2b/cargo/integration/v2'
        settings.YANDEX_SHOP_LAT = 53.2169
        settings.YANDEX_SHOP_LON = 50.1627
        settings.YANDEX_SHOP_ADDRESS = 'Самара, ул. Революционная, д. 3'
        settings.YANDEX_PVZ_ID = 'test-pvz-id'
        settings.YANDEX_PVZ_LAT = 53.2008
        settings.YANDEX_PVZ_LON = 50.1505
        settings.YANDEX_PVZ_ADDRESS = 'г. Самара, ул. Лукачева, д. 6'
        settings.YANDEX_DELIVERY_TEST_MODE = False
        return YandexDeliveryService()

    def test_build_items_express_format(self, service, order_with_items):
        result = service.build_items_payload(
            order_with_items.items.all(),
            api_type='express'
        )

        assert len(result) == 1
        item = result[0]
        assert 'title' in item
        assert 'quantity' in item
        assert 'cost_value' in item
        assert 'cost_currency' in item
        assert 'size' in item
        assert 'weight' in item

    def test_build_items_other_day_format(self, service, order_with_items):
        result = service.build_items_payload(
            order_with_items.items.all(),
            api_type='other_day'
        )

        assert len(result) == 1
        item = result[0]
        assert 'count' in item
        assert 'name' in item
        assert 'physical_dims' in item
        assert 'dx' in item['physical_dims']
        assert 'dy' in item['physical_dims']
        assert 'dz' in item['physical_dims']
