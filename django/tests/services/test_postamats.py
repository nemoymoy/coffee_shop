"""Tests for YandexDeliveryService.get_postamats() — terminal/pickup points API."""
import pytest
from unittest.mock import patch, MagicMock
from django.core.cache import cache
from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService


pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def clear_cache():
    """Clear Django cache before each test to prevent cache interference."""
    cache.clear()


class TestGetPostamats:
    """Tests for postamat (terminal) fetching from Yandex Delivery API."""

    @pytest.fixture
    def mock_terminal_point(self):
        """Return a mock terminal (postamat) point from Yandex API.

        Note: Yandex API uses 'terminal' type for postamats.
        """
        return {
            'id': 'terminal-001',
            'name': 'Постомат Яндекс Самара',
            'type': 'terminal',
            'operator_id': 'market_l4g',
            'position': {'latitude': 53.21, 'longitude': 50.16},
            'address': {
                'full_address': 'Самара, ул. Молодогвардейская, д. 123',
            },
            'work_schedule': {
                'days': [
                    {'day_name': 'Пн-Пт', 'time_range': '08:00-23:00'},
                    {'day_name': 'Сб-Вс', 'time_range': '09:00-22:00'},
                ],
            },
        }

    @pytest.fixture
    def mock_pvz_point(self):
        """Return a mock PVZ (pickup point) from Yandex API."""
        return {
            'id': 'pvz-001',
            'name': 'ПВЗ Яндекс Маркет',
            'type': 'pickup_point',
            'operator_id': 'market_l4g',
            'position': {'latitude': 53.22, 'longitude': 50.17},
            'address': {
                'full_address': 'Самара, ул. Ленинградская, д. 45',
            },
            'work_schedule': {
                'days': [
                    {'day_name': 'Ежедневно', 'time_range': '09:00-21:00'},
                ],
            },
        }

    @pytest.fixture
    def mock_api_response(self, mock_terminal_point, mock_pvz_point):
        """Return a mock API response with mixed point types.

        Note: Yandex API returns both 'terminal' (postamats) and 'pickup_point' (PVZ)
        when queried without type filter, but our code requests 'terminal' directly.
        """
        return {
            'points': [mock_terminal_point, mock_pvz_point],
        }

    def test_get_postamats_not_configured(self, settings):
        """When API is not configured, returns error."""
        settings.YANDEX_DELIVERY_TOKEN = ''
        service = YandexDeliveryService()
        result = service.get_postamats()

        assert result['success'] is False
        assert 'не настроена' in result['error'].lower()

    def test_get_postamats_filters_terminals_only(
        self, settings, mock_api_response
    ):
        """Only terminal points are returned (type=terminal).

        Note: API returns both 'terminal' and 'pickup_point' types.
        Our code requests 'terminal' type directly and filters server-side.
        """
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token-test'

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = mock_api_response

        with patch('requests.post', return_value=mock_response):
            service = YandexDeliveryService()
            result = service.get_postamats(
                center_lat=53.2169,
                center_lon=50.1627,
                radius_km=50,
            )

        assert result['success'] is True
        assert result['count'] == 1
        assert result['points'][0]['type'] == 'terminal'
        assert result['points'][0]['id'] == 'terminal-001'
        # PVZ should be filtered out
        types = [p['type'] for p in result['points']]
        assert 'pickup_point' not in types

    def test_get_postamats_empty_when_no_terminals(
        self, settings, mock_pvz_point
    ):
        """When only PVZ points exist, returns empty list (not error)."""
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token-test'

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {
            'points': [mock_pvz_point],
        }

        with patch('requests.post', return_value=mock_response):
            service = YandexDeliveryService()
            result = service.get_postamats(
                center_lat=53.2169,
                center_lon=50.1627,
                radius_km=50,
            )

        assert result['success'] is True
        assert result['count'] == 0
        assert result['points'] == []
        assert 'недоступны' in result.get('message', '').lower()

    def test_get_postamats_geo_filter_out_of_range(
        self, settings, mock_terminal_point
    ):
        """Points outside radius are filtered out."""
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token-test'

        # Point very far from shop (e.g., Moscow)
        far_point = dict(mock_terminal_point)
        far_point['position'] = {'latitude': 55.75, 'longitude': 37.62}
        far_point['address']['full_address'] = 'Москва, ул. Тестовая, 1'

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'points': [far_point]}

        with patch('requests.post', return_value=mock_response):
            service = YandexDeliveryService()
            result = service.get_postamats(
                center_lat=53.2169,
                center_lon=50.1627,
                radius_km=50,
            )

        assert result['success'] is True
        assert result['count'] == 0

    def test_get_postamats_normalizes_point_data(
        self, settings, mock_terminal_point
    ):
        """Returned points have normalized schema."""
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token-test'

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'points': [mock_terminal_point]}

        with patch('requests.post', return_value=mock_response):
            service = YandexDeliveryService()
            result = service.get_postamats(
                center_lat=53.2169,
                center_lon=50.1627,
                radius_km=50,
            )

        point = result['points'][0]
        required_fields = [
            'id', 'name', 'address', 'latitude', 'longitude',
            'operator_id', 'type', 'work_schedule', 'distance_km',
        ]
        for field in required_fields:
            assert field in point, f'Missing field: {field}'

        assert point['id'] == 'terminal-001'
        assert point['type'] == 'terminal'
        assert point['operator_id'] == 'market_l4g'
        assert isinstance(point['distance_km'], (int, float))

    def test_get_postamats_sorted_by_distance(
        self, settings
    ):
        """Points are sorted by distance (closest first)."""
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token-test'

        # Create points at different distances from shop
        points = [
            {
                'id': f'terminal-{i}',
                'name': f'Постомат {i}',
                'type': 'terminal',
                'operator_id': 'market_l4g',
                'position': {'latitude': 53.21 + i * 0.001, 'longitude': 50.16 + i * 0.001},
                'address': {'full_address': f'Адрес {i}'},
                'work_schedule': {},
            }
            for i in range(5, 0, -1)  # Far to near
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'points': points}

        with patch('requests.post', return_value=mock_response):
            service = YandexDeliveryService()
            result = service.get_postamats(
                center_lat=53.2169,
                center_lon=50.1627,
                radius_km=50,
            )

        distances = [p['distance_km'] for p in result['points']]
        assert distances == sorted(distances), 'Points must be sorted by distance'

    def test_get_postamats_api_error(self, settings):
        """Handles API errors gracefully."""
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token-test'

        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_response.text = 'Internal Server Error'

        with patch('requests.post', return_value=mock_response):
            service = YandexDeliveryService()
            result = service.get_postamats()

        assert result['success'] is False
        assert '500' in result['error']

    def test_get_postamats_unauthorized(self, settings):
        """Handles 401 Unauthorized (invalid token)."""
        settings.YANDEX_DELIVERY_TOKEN = 'invalid-token'

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_response.text = 'Unauthorized'

        with patch('requests.post', return_value=mock_response):
            service = YandexDeliveryService()
            result = service.get_postamats()

        assert result['success'] is False
        assert 'токен' in result['error'].lower() or '401' in result['error']

    def test_get_postamats_rate_limit_retry(self, settings):
        """Retries on 429 Too Many Requests."""
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token-test'

        mock_response_429 = MagicMock()
        mock_response_429.status_code = 429

        mock_response_200 = MagicMock()
        mock_response_200.status_code = 200
        mock_response_200.json.return_value = {
            'points': [{
                'id': 'terminal-001',
                'name': 'Постомат',
                'type': 'terminal',
                'operator_id': 'market_l4g',
                'position': {'latitude': 53.21, 'longitude': 50.16},
                'address': {'full_address': 'Самара, ул. Тестовая, 1'},
                'work_schedule': {},
            }],
        }

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return mock_response_429
            return mock_response_200

        with patch('requests.post', side_effect=side_effect):
            service = YandexDeliveryService()
            result = service.get_postamats()

        assert result['success'] is True
        assert call_count[0] == 2  # 429 + retry

    def test_get_postamats_max_results_limit(self, settings):
        """Respects max_results limit."""
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token-test'

        # Create 20 terminal points (type=terminal for postamats)
        points = [
            {
                'id': f'terminal-{i}',
                'name': f'Постомат {i}',
                'type': 'terminal',
                'operator_id': 'market_l4g',
                'position': {'latitude': 53.21 + i * 0.0001, 'longitude': 50.16 + i * 0.0001},
                'address': {'full_address': f'Адрес {i}'},
                'work_schedule': {},
            }
            for i in range(20)
        ]

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = {'points': points}

        with patch('requests.post', return_value=mock_response):
            service = YandexDeliveryService()
            result = service.get_postamats(max_results=5)

        assert result['success'] is True
        assert result['count'] == 5
        assert len(result['points']) <= 5


class TestFetchPostamatsPagination:
    """Tests for pagination handling in _fetch_postamats."""

    def test_pagination_fetches_all_pages(self, settings):
        """Fetches multiple pages when there are more points than page_size.

        Note: API uses type='terminal' for postamats.
        """
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token-test'

        # Page 1: 100 points (page_size) - all terminal type
        page1_points = [
            {
                'id': f'terminal-{i}',
                'name': f'Постомат {i}',
                'type': 'terminal',
                'operator_id': 'market_l4g',
                'position': {'latitude': 53.21, 'longitude': 50.16},
                'address': {'full_address': f'Адрес {i}'},
                'work_schedule': {},
            }
            for i in range(100)
        ]

        # Page 2: 50 points (remaining)
        page2_points = [
            {
                'id': f'terminal-{i}',
                'name': f'Постомат {i}',
                'type': 'terminal',
                'operator_id': 'market_l4g',
                'position': {'latitude': 53.21, 'longitude': 50.16},
                'address': {'full_address': f'Адрес {i}'},
                'work_schedule': {},
            }
            for i in range(100, 150)
        ]

        call_count = [0]

        def side_effect(*args, **kwargs):
            call_count[0] += 1
            mock = MagicMock()
            if call_count[0] == 1:
                mock.status_code = 200
                mock.json.return_value = {'points': page1_points}
            else:
                mock.status_code = 200
                mock.json.return_value = {'points': page2_points}
            return mock

        with patch('requests.post', side_effect=side_effect):
            service = YandexDeliveryService()
            result = service.get_postamats()

        assert result['success'] is True
        # All 150 terminals should be fetched (before geo-filter)
        assert call_count[0] == 2  # Two pages fetched


class TestHaversineDistance:
    """Tests for _haversine_distance utility."""

    def test_same_location(self, settings):
        """Distance between same coordinates is 0."""
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        service = YandexDeliveryService()
        distance = service._haversine_distance(53.21, 50.16, 53.21, 50.16)
        assert distance == pytest.approx(0, abs=0.01)

    def test_known_distance(self, settings):
        """Distance between Moscow and Samara is approximately 880 km."""
        settings.YANDEX_DELIVERY_TOKEN = 'dev-token'
        service = YandexDeliveryService()
        # Moscow: 55.7558, 37.6173; Samara: 53.2169, 50.1627
        distance = service._haversine_distance(
            53.2169, 50.1627,
            55.7558, 37.6173,
        )
        # Approximately 880 km (allowing some tolerance)
        assert 850 <= distance <= 920
