"""Tests for Other Day API (scheduled delivery)."""
from unittest.mock import MagicMock, patch

import pytest
import requests

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
                'dx': 12,  # cm
                'dy': 6,   # cm
                'dz': 6,   # cm
            },
        }]

    def test_create_order_courier_success(self, service, other_day_items):
        """Test courier delivery: offers/create → offers/confirm → request/info."""
        # offers/create response
        offers_create_response = MagicMock()
        offers_create_response.status_code = 200
        offers_create_response.json.return_value = {
            'offers': [{'offer_id': 'offer-courier-123'}]
        }

        # offers/confirm response
        offers_confirm_response = MagicMock()
        offers_confirm_response.status_code = 200
        offers_confirm_response.json.return_value = {
            'request_id': 'req-123',
        }

        # request/info response
        request_info_response = MagicMock()
        request_info_response.status_code = 200
        request_info_response.json.return_value = {
            'request_id': 'req-123',
            'status': 'new',
            'tracking_number': 'TRACK-456',
        }

        side_effects = [
            offers_create_response,
            offers_confirm_response,
        ]

        with patch.object(
            service.session, 'post', side_effect=side_effects
        ):
            with patch.object(service.session, 'get', return_value=request_info_response):
                result = service.create_order(
                    items=other_day_items,
                    places=[{'barcode': 'BOX-001'}],
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
            assert result['offer_id'] == 'offer-courier-123'

    def test_create_order_pvz_success_with_offers(self, service, other_day_items):
        """Test PVZ delivery with available offers (offers/info → offers/create → confirm)."""
        # offers/info returns available intervals
        offers_info_response = MagicMock()
        offers_info_response.status_code = 200
        offers_info_response.json.return_value = {
            'offers': [
                {
                    'offer_id': 'offer-pvz-123',
                    'expires_at': '2026-09-15T15:00:00.000000Z',
                    'delivery_interval': {
                        'from': '2026-09-15T10:00:00.000000Z',
                        'to': '2026-09-15T14:00:00.000000Z',
                    },
                    'pickup_interval': {
                        'min': '2026-09-15T09:00:00.000000Z',
                        'max': '2026-09-15T09:30:00.000000Z',
                    },
                }
            ],
        }

        # offers/create response
        offers_create_response = MagicMock()
        offers_create_response.status_code = 200
        offers_create_response.json.return_value = {
            'offers': [
                {
                    'offer_id': 'offer-pvz-created-456',
                    'expires_at': '2026-09-15T15:00:00.000000Z',
                }
            ],
        }

        # offers/confirm response
        offers_confirm_response = MagicMock()
        offers_confirm_response.status_code = 200
        offers_confirm_response.json.return_value = {
            'request_id': 'req-pvz-456',
        }

        # request/info response
        request_info_response = MagicMock()
        request_info_response.status_code = 200
        request_info_response.json.return_value = {
            'request_id': 'req-pvz-456',
            'status': 'new',
            'tracking_number': 'TRACK-PVZ-789',
            'pricing': {'total': '192.15', 'currency': 'RUB'},
            'delivery_interval': {
                'from': '2026-09-15T10:00:00.000000Z',
                'to': '2026-09-15T14:00:00.000000Z',
            },
        }

        side_effects = [
            offers_info_response,
            offers_create_response,
            offers_confirm_response,
        ]

        with patch.object(
            service.session, 'post', side_effect=side_effects
        ):
            with patch.object(service.session, 'get', return_value=request_info_response):
                result = service.create_order(
                    items=other_day_items,
                    places=[{'barcode': 'BOX-001'}],
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
            assert result['request_id'] == 'req-pvz-456'
            assert result['method'] == 'offers'
            assert result['status'] == 'new'
            assert result['offer_id'] == 'offer-pvz-created-456'
            assert result['delivery_date'] == '15.09.2026'
            # UTC 10:00-14:00 → Samara (UTC+4) 14:00-18:00
            assert result['delivery_time'] == '14:00–18:00'
            assert result['price'] == '192.15'
            assert result['currency'] == 'RUB'

    def test_create_order_pvz_success_with_request_create(self, service, other_day_items):
        """Test PVZ delivery when no offers available (uses request/create)."""
        # offers/info returns no valid offers
        offers_info_response = MagicMock()
        offers_info_response.status_code = 200
        offers_info_response.json.return_value = {
            'offers': [],
        }

        # request/create response
        request_create_response = MagicMock()
        request_create_response.status_code = 200
        request_create_response.json.return_value = {
            'request_id': 'req-pvz-request-789',
        }

        # request/info response
        request_info_response = MagicMock()
        request_info_response.status_code = 200
        request_info_response.json.return_value = {
            'request_id': 'req-pvz-request-789',
            'status': 'new',
            'tracking_number': 'TRACK-REQUEST-001',
            'pricing': {'total': '250.00', 'currency': 'RUB'},
            'delivery_interval': {
                'from': '2026-09-16T12:00:00.000000Z',
                'to': '2026-09-16T16:00:00.000000Z',
            },
        }

        side_effects = [
            offers_info_response,
            request_create_response,
        ]

        with patch.object(
            service.session, 'post', side_effect=side_effects
        ):
            with patch.object(service.session, 'get', return_value=request_info_response):
                result = service.create_order(
                    items=other_day_items,
                    places=[{'barcode': 'BOX-001'}],
                    client_order_id='order-3',
                    destination_coords=[50.15, 53.20],
                    destination_address='Самара, ул. Мира, 10',
                    delivery_type='postamat',
                    pvz_id='postamat-id-123',
                    recipient_name='Анна Сидорова',
                    recipient_phone='+79001234568',
                    email='anna@example.com',
                )

            assert result['success'] is True
            assert result['request_id'] == 'req-pvz-request-789'
            assert result['method'] == 'request'
            assert result['status'] == 'new'
            assert result['delivery_date'] == '16.09.2026'
            # UTC 12:00-16:00 → Samara (UTC+4) 16:00-20:00
            assert result['delivery_time'] == '16:00–20:00'
            assert result['price'] == '250.0'

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

        with patch.object(service.session, 'get', return_value=mock_response):
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


class TestOtherDayDeliveryErrors:
    """Tests for Other Day API error handling."""

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

    def test_create_order_pvz_no_delivery_options(self, service):
        """Test when delivery is not available (no_delivery_options error)."""
        import requests as requests_lib

        # offers/info returns no valid offers
        offers_info_response = MagicMock()
        offers_info_response.status_code = 200
        offers_info_response.json.return_value = {'offers': []}

        # request/create returns no_delivery_options error
        no_options_response = MagicMock()
        no_options_response.status_code = 400
        no_options_response.json.return_value = {
            'code': 'no_delivery_options',
            'message': 'Доставка недоступна',
        }
        no_options_response.raise_for_status = MagicMock(
            side_effect=requests_lib.HTTPError(response=no_options_response)
        )

        side_effects = [offers_info_response, no_options_response]

        with patch.object(
            service.session, 'post', side_effect=side_effects
        ):
            result = service.create_order(
                items=[{'count': 1, 'name': 'Test'}],
                places=[{'barcode': 'BOX-001'}],
                client_order_id='order-error',
                destination_coords=[],
                destination_address='',
                delivery_type='pickup',
                pvz_id='pvz-id',
                recipient_name='Test User',
                recipient_phone='+79000000000',
                email='test@example.com',
            )

        # Should fail with HTTP error from request/create
        assert result['success'] is False

    def test_create_order_pvz_offer_expired(self, service):
        """Test when offer expires before confirmation."""
        import requests as requests_lib

        # offers/info returns offers
        offers_info_response = MagicMock()
        offers_info_response.status_code = 200
        offers_info_response.json.return_value = {
            'offers': [
                {
                    'offer_id': 'offer-expiring',
                    'delivery_interval': {
                        'from': '2026-09-15T10:00:00.000000Z',
                        'to': '2026-09-15T14:00:00.000000Z',
                    },
                }
            ],
        }

        # offers/create succeeds
        offers_create_response = MagicMock()
        offers_create_response.status_code = 200
        offers_create_response.json.return_value = {
            'offers': [{'offer_id': 'offer-expired-123'}]
        }

        # offers/confirm fails (offer expired)
        expired_response = MagicMock()
        expired_response.status_code = 400
        expired_response.json.return_value = {
            'code': 'offer_expired',
            'message': 'Оффер истёк',
        }
        expired_response.raise_for_status = MagicMock(
            side_effect=requests_lib.HTTPError(response=expired_response)
        )

        side_effects = [
            offers_info_response,
            offers_create_response,
            expired_response,
        ]

        with patch.object(
            service.session, 'post', side_effect=side_effects
        ):
            result = service.create_order(
                items=[{'count': 1, 'name': 'Test'}],
                places=[{'barcode': 'BOX-001'}],
                client_order_id='order-expired',
                destination_coords=[],
                destination_address='',
                delivery_type='pickup',
                pvz_id='pvz-id',
                recipient_name='Test User',
                recipient_phone='+79000000000',
                email='test@example.com',
            )

        # Should fail with HTTP error
        assert result['success'] is False

    def test_create_order_pvz_request_info_timeout(self, service):
        """Test when request/info times out (no price/status received)."""
        # offers/info returns offers
        offers_info_response = MagicMock()
        offers_info_response.status_code = 200
        offers_info_response.json.return_value = {
            'offers': [
                {
                    'offer_id': 'offer-timeout',
                    'delivery_interval': {
                        'from': '2026-09-15T10:00:00.000000Z',
                        'to': '2026-09-15T14:00:00.000000Z',
                    },
                }
            ],
        }

        # offers/create succeeds
        offers_create_response = MagicMock()
        offers_create_response.status_code = 200
        offers_create_response.json.return_value = {
            'offers': [{'offer_id': 'offer-timeout-123'}]
        }

        # offers/confirm succeeds
        offers_confirm_response = MagicMock()
        offers_confirm_response.status_code = 200
        offers_confirm_response.json.return_value = {
            'request_id': 'req-timeout-123',
        }

        # request/info keeps returning empty data (simulating timeout)
        timeout_response = MagicMock()
        timeout_response.status_code = 200
        timeout_response.json.return_value = {
            'request_id': 'req-timeout-123',
            'status': 'pending',
            'pricing': {},
            'delivery_interval': {},
        }

        side_effects = [
            offers_info_response,
            offers_create_response,
            offers_confirm_response,
        ] + [timeout_response] * 10

        with patch.object(
            service.session, 'post', side_effect=side_effects
        ):
            result = service.create_order(
                items=[{'count': 1, 'name': 'Test'}],
                places=[{'barcode': 'BOX-001'}],
                client_order_id='order-timeout',
                destination_coords=[],
                destination_address='',
                delivery_type='pickup',
                pvz_id='pvz-id',
                recipient_name='Test User',
                recipient_phone='+79000000000',
                email='test@example.com',
            )

        assert result['success'] is False
        assert result['error'] == 'timeout'


class TestOtherDayStatusMapping:
    """Tests for Other Day API status mapping."""

    def test_other_day_delivered_statuses(self):
        from coffee_shop.tasks import (
            OTHER_DAY_DELIVERED_STATUSES, _map_yandex_status_to_order
        )
        assert 'delivered_to_address' in OTHER_DAY_DELIVERED_STATUSES
        assert 'delivered_to_point' in OTHER_DAY_DELIVERED_STATUSES
        assert 'finished' in OTHER_DAY_DELIVERED_STATUSES

    def test_other_day_in_progress_statuses(self):
        from coffee_shop.tasks import (
            OTHER_DAY_IN_PROGRESS_STATUSES, _map_yandex_status_to_order
        )
        assert 'created' in OTHER_DAY_IN_PROGRESS_STATUSES
        assert 'in_work' in OTHER_DAY_IN_PROGRESS_STATUSES
        assert 'picked_up' in OTHER_DAY_IN_PROGRESS_STATUSES
        assert 'delivered' in OTHER_DAY_IN_PROGRESS_STATUSES

    def test_map_other_day_finished(self):
        from coffee_shop.tasks import _map_yandex_status_to_order
        order_status, is_final = _map_yandex_status_to_order(
            'finished', api_type='other_day'
        )
        assert order_status == 'delivered'
        assert is_final is True

    def test_map_other_day_in_work(self):
        from coffee_shop.tasks import _map_yandex_status_to_order
        order_status, is_final = _map_yandex_status_to_order(
            'in_work', api_type='other_day'
        )
        assert order_status == 'in_progress'
        assert is_final is False



