"""Tests for Express API (same-day delivery)."""
import json
from unittest.mock import MagicMock, patch

import pytest
from django.test import RequestFactory
from rest_framework.test import APIClient

from coffee_shop.apps.orders.models import Order
from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService


class TestExpressDeliveryService:
    """Tests for Express API methods."""

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
    def express_items(self):
        return [{
            'title': 'Кофе 250г',
            'quantity': 2,
            'cost_value': '500',
            'cost_currency': 'RUB',
            'size': {'length': 0.12, 'width': 0.06, 'height': 0.06},
            'weight': 0.3,
        }]

    @pytest.fixture
    def express_route_points(self):
        return [
            {
                'point_id': 1,
                'visit_order': 1,
                'type': 'source',
                'contact': {'name': 'Магазин', 'phone': ''},
                'address': {
                    'fullname': 'Самара, ул. Революционная, д. 3',
                    'coordinates': [50.1627, 53.2169],
                },
            },
            {
                'point_id': 2,
                'visit_order': 2,
                'type': 'destination',
                'contact': {'name': 'Иван Петров', 'phone': '+79001234567'},
                'address': {
                    'fullname': 'Москва, ул. Арбат, 10',
                    'coordinates': [37.59, 55.75],
                },
            },
        ]

    def test_create_express_claim_success(self, service, express_items, express_route_points):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 'claim-123',
            'status': 'new',
            'cost': {'value': '450'},
        }

        with patch.object(service.session, 'post', return_value=mock_response):
            result = service.create_express_claim(
                items=express_items,
                route_points=express_route_points,
                client_requirements={'taxi_class': 'courier'},
            )

        assert result['success'] is True
        assert result['claim_id'] == 'claim-123'
        assert result['status'] == 'new'
        assert 'request_id' in result

    def test_create_express_claim_no_token(self, settings):
        settings.YANDEX_DELIVERY_TOKEN = ''
        service = YandexDeliveryService()
        result = service.create_express_claim(
            items=[], route_points=[]
        )
        assert result['success'] is False
        assert 'не настроена' in result['error']

    def test_accept_express_claim_success(self, service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 'claim-123',
            'status': 'accepted',
        }

        with patch.object(service.session, 'post', return_value=mock_response):
            result = service.accept_express_claim('claim-123')

        assert result['success'] is True
        assert result['claim_id'] == 'claim-123'
        assert result['status'] == 'accepted'

    def test_get_express_claim_info_success(self, service):
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'id': 'claim-123',
            'status': 'performer_found',
        }

        with patch.object(service.session, 'post', return_value=mock_response):
            result = service.get_express_claim_info('claim-123')

        assert result['success'] is True
        assert result['status'] == 'performer_found'
        assert result['claim_id'] == 'claim-123'

    def test_is_configured_with_valid_token(self, service):
        assert service.is_configured() is True

    def test_is_configured_without_token(self, settings):
        settings.YANDEX_DELIVERY_TOKEN = ''
        service = YandexDeliveryService()
        assert service.is_configured() is False


class TestExpressClaimView:
    """Tests for Express API views."""

    @pytest.fixture
    def client(self):
        return APIClient()

    @pytest.fixture
    def factory(self):
        return RequestFactory()

    def test_determine_api_type_courier(self):
        """Courier → Express API."""
        from coffee_shop.apps.orders.views.delivery_views import _determine_api_type
        assert _determine_api_type('courier') == 'express'

    def test_determine_api_type_pickup(self):
        """PVZ → Other Day API."""
        from coffee_shop.apps.orders.views.delivery_views import _determine_api_type
        assert _determine_api_type('pickup') == 'other_day'

    def test_determine_api_type_postamat(self):
        """Postamat → Other Day API."""
        from coffee_shop.apps.orders.views.delivery_views import _determine_api_type
        assert _determine_api_type('postamat') == 'other_day'


class TestExpressStatusMapping:
    """Tests for Express API status mapping."""

    def test_delivered_statuses(self):
        from coffee_shop.apps.orders.tasks import (
            EXPRESS_DELIVERED_STATUSES, _map_yandex_status_to_order
        )
        assert 'delivered' in EXPRESS_DELIVERED_STATUSES
        assert 'delivered_to_address' in EXPRESS_DELIVERED_STATUSES
        assert 'delivered_to_point' in EXPRESS_DELIVERED_STATUSES
        assert 'delivered_finish' in EXPRESS_DELIVERED_STATUSES

    def test_in_progress_statuses(self):
        from coffee_shop.apps.orders.tasks import (
            EXPRESS_IN_PROGRESS_STATUSES, _map_yandex_status_to_order
        )
        assert 'accepted' in EXPRESS_IN_PROGRESS_STATUSES
        assert 'performer_found' in EXPRESS_IN_PROGRESS_STATUSES
        assert 'pickup_arrived' in EXPRESS_IN_PROGRESS_STATUSES
        assert 'pickuped' in EXPRESS_IN_PROGRESS_STATUSES

    def test_map_delivered_status(self):
        from coffee_shop.apps.orders.tasks import _map_yandex_status_to_order
        order_status, is_final = _map_yandex_status_to_order(
            'delivered', api_type='express'
        )
        assert order_status == 'delivered'
        assert is_final is True

    def test_map_in_progress_status(self):
        from coffee_shop.apps.orders.tasks import _map_yandex_status_to_order
        order_status, is_final = _map_yandex_status_to_order(
            'performer_found', api_type='express'
        )
        assert order_status == 'in_progress'
        assert is_final is False

    def test_map_new_status_no_update(self):
        from coffee_shop.apps.orders.tasks import _map_yandex_status_to_order
        order_status, is_final = _map_yandex_status_to_order(
            'new', api_type='express'
        )
        assert order_status is None
        assert is_final is False

    def test_map_rejected_status(self):
        from coffee_shop.apps.orders.tasks import _map_yandex_status_to_order
        order_status, is_final = _map_yandex_status_to_order(
            'rejection', api_type='express'
        )
        assert order_status == 'canceled'
        assert is_final is True

    def test_other_day_delivered_status(self):
        from coffee_shop.apps.orders.tasks import _map_yandex_status_to_order
        order_status, is_final = _map_yandex_status_to_order(
            'finished', api_type='other_day'
        )
        assert order_status == 'delivered'
        assert is_final is True


class TestOrderModelNewFields:
    """Tests for new Order model fields."""

    def test_delivery_api_type_choices(self):
        assert hasattr(Order, 'DELIVERY_API_TYPE_CHOICES')
        choices = dict(Order.DELIVERY_API_TYPE_CHOICES)
        assert 'express' in choices
        assert 'other_day' in choices

    def test_delivery_type_has_postamat(self):
        assert hasattr(Order.DeliveryType, 'POSTAMAT')
        assert Order.DeliveryType.POSTAMAT == 'postamat'

    def test_order_has_new_fields(self):
        """Check that all new fields exist on the Order model."""
        field_names = [f.name for f in Order._meta.get_fields()]
        assert 'client_order_id' in field_names
        assert 'delivery_interval_from' in field_names
        assert 'delivery_interval_to' in field_names
        assert 'recipient_name' in field_names
        assert 'recipient_phone' in field_names
        assert 'delivery_api_type' in field_names
        assert 'express_claim_id' in field_names
