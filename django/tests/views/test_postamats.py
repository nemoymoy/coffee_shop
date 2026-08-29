"""Tests for postamats_list_view — POST /checkout/postamats/."""
import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

pytestmark = pytest.mark.django_db(transaction=True)


class TestPostamatsListView:
    """Tests for /checkout/postamats/ endpoint."""

    @pytest.fixture
    def authenticated_client(self, client):
        """Return an authenticated test client."""
        user = User.objects.create_user(
            username='testuser',
            password='testpass123',
        )
        client.force_login(user)
        return client

    def test_postamats_list_returns_success(self, authenticated_client):
        """Successful response returns success=True with points."""
        mock_points = [
            {
                'id': 'terminal-001',
                'name': 'Постомат Яндекс',
                'address': 'Самара, ул. Тестовая, 1',
                'latitude': 53.21,
                'longitude': 50.16,
                'operator_id': 'market_l4g',
                'type': 'terminal',
                'work_schedule': {},
                'distance_km': 2.5,
            },
        ]

        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_postamats.return_value = {
                'success': True,
                'points': mock_points,
                'count': 1,
            }
            MockService.return_value = mock_instance

            response = authenticated_client.get(reverse('orders:postamats_list'))

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['count'] == 1
        assert len(data['points']) == 1
        assert data['points'][0]['id'] == 'terminal-001'

    def test_postamats_list_returns_empty(self, authenticated_client):
        """When no postamats found, returns success=True with empty list."""
        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_postamats.return_value = {
                'success': True,
                'points': [],
                'count': 0,
                'message': 'Постоматы в вашем регионе недоступны',
            }
            MockService.return_value = mock_instance

            response = authenticated_client.get(reverse('orders:postamats_list'))

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['count'] == 0
        assert data['points'] == []
        assert data.get('message') == 'Постоматы в вашем регионе недоступны'

    def test_postamats_list_returns_error(self, authenticated_client):
        """When API fails, returns success=False with error message."""
        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_postamats.return_value = {
                'success': False,
                'error': 'Таймаут запроса к API',
            }
            MockService.return_value = mock_instance

            response = authenticated_client.get(reverse('orders:postamats_list'))

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False
        assert data['error'] == 'Таймаут запроса к API'
        assert data['count'] == 0

    def test_postamats_list_unauthenticated(self, client):
        """Unauthenticated users cannot access postamats list."""
        response = client.get(reverse('orders:postamats_list'))
        # Should redirect to login
        assert response.status_code in (302, 403)

    def test_postamats_list_with_radius_param(self, authenticated_client):
        """Custom radius_km parameter is passed to service."""
        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_postamats.return_value = {
                'success': True,
                'points': [],
                'count': 0,
            }
            MockService.return_value = mock_instance

            response = authenticated_client.get(
                reverse('orders:postamats_list'),
                {'radius_km': 30},
            )

        assert response.status_code == 200
        # Verify service was called with custom radius
        call_kwargs = mock_instance.get_postamats.call_args
        assert call_kwargs.kwargs['radius_km'] == 30.0

    def test_postamats_list_with_max_results_param(self, authenticated_client):
        """Custom max_results parameter is passed to service."""
        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_postamats.return_value = {
                'success': True,
                'points': [],
                'count': 0,
            }
            MockService.return_value = mock_instance

            response = authenticated_client.get(
                reverse('orders:postamats_list'),
                {'max_results': 100},
            )

        assert response.status_code == 200
        call_kwargs = mock_instance.get_postamats.call_args
        assert call_kwargs.kwargs['max_results'] == 100

    def test_postamats_list_invalid_radius_param(self, authenticated_client):
        """Invalid radius_km parameter returns 400."""
        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_postamats.return_value = {
                'success': True,
                'points': [],
                'count': 0,
            }
            MockService.return_value = mock_instance

            response = authenticated_client.get(
                reverse('orders:postamats_list'),
                {'radius_km': 'not_a_number'},
            )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'параметры' in data['error'].lower() or 'parameters' in data['error'].lower()

    def test_postamats_list_clamps_radius(self, authenticated_client):
        """Radius is clamped to valid range [1, 200]."""
        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_postamats.return_value = {
                'success': True,
                'points': [],
                'count': 0,
            }
            MockService.return_value = mock_instance

            # radius_km=0 should be clamped to 1
            response = authenticated_client.get(
                reverse('orders:postamats_list'),
                {'radius_km': 0},
            )

        assert response.status_code == 200
        call_kwargs = mock_instance.get_postamats.call_args
        assert call_kwargs.kwargs['radius_km'] >= 1

            # radius_km=300 should be clamped to 200
        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_postamats.return_value = {
                'success': True,
                'points': [],
                'count': 0,
            }
            MockService.return_value = mock_instance

            response = authenticated_client.get(
                reverse('orders:postamats_list'),
                {'radius_km': 300},
            )

        assert response.status_code == 200
        call_kwargs = mock_instance.get_postamats.call_args
        assert call_kwargs.kwargs['radius_km'] <= 200

    def test_postamats_list_point_schema(self, authenticated_client):
        """Returned points have the correct schema."""
        mock_point = {
            'id': 'terminal-123',
            'name': 'Постомат Тестовый',
            'address': 'Самара, ул. Тестовая, д. 10',
            'latitude': 53.2169,
            'longitude': 50.1627,
            'operator_id': 'market_l4g',
            'type': 'terminal',
            'work_schedule': {
                'days': [
                    {'day_name': 'Пн-Пт', 'time_range': '08:00-23:00'},
                ],
            },
            'distance_km': 3.7,
        }

        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_postamats.return_value = {
                'success': True,
                'points': [mock_point],
                'count': 1,
            }
            MockService.return_value = mock_instance

            response = authenticated_client.get(reverse('orders:postamats_list'))

        assert response.status_code == 200
        data = response.json()
        point = data['points'][0]

        # Verify all expected fields
        assert point['id'] == 'terminal-123'
        assert point['name'] == 'Постомат Тестовый'
        assert point['address'] == 'Самара, ул. Тестовая, д. 10'
        assert point['latitude'] == 53.2169
        assert point['longitude'] == 50.1627
        assert point['operator_id'] == 'market_l4g'
        assert point['type'] == 'terminal'
        assert point['work_schedule'] == mock_point['work_schedule']
        assert point['distance_km'] == 3.7
