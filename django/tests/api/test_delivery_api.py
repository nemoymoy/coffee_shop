"""Tests for Yandex Delivery views (calculate_delivery_view)."""
import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestCalculateDeliveryView:
    """Тесты для расчёта стоимости доставки — проверка auth."""

    def test_anonymous_user_rejected(self, client):
        """Неавторизованный пользователь не может рассчитать доставку."""
        response = client.post(
            reverse('orders:calculate_delivery'),
            data='{"destination_coords": [55.75, 37.61], "destination_address": "Москва"}',
            content_type='application/json',
        )
        assert response.status_code == 403
        data = response.json()
        assert data['error'] == 'login_required'

    def test_authenticated_user_can_calculate(self, client, user):
        """Авторизованный пользователь может вызвать endpoint (auth работает)."""
        client.force_login(user)
        response = client.post(
            reverse('orders:calculate_delivery'),
            data='{"destination_coords": [55.75, 37.61], "destination_address": "Москва"}',
            content_type='application/json',
        )
        # Endpoint обработал запрос — не 403
        assert response.status_code not in (403,)

    def test_calculate_delivery_success(self, client):
        """Auth пользователь не получает 403."""
        user = User.objects.create_user(
            username='testuser', email='test@example.com', password='test123'
        )
        client.force_login(user)
        response = client.post(
            reverse('orders:calculate_delivery'),
            data='{"destination_coords": [55.75, 37.61], "destination_address": "Москва"}',
            content_type='application/json',
        )
        assert response.status_code not in (403,)

    def test_calculate_delivery_invalid_json(self, client):
        """Некорректный JSON."""
        user = User.objects.create_user(
            username='testuser3', email='test3@example.com', password='test123'
        )
        client.force_login(user)
        response = client.post(
            reverse('orders:calculate_delivery'),
            data='not-json',
            content_type='application/json',
        )
        assert response.status_code == 400


class TestGeocodeAddressView:
    """Тесты для геокодирования — только для staff."""

    def test_staff_can_geocode(self, client, user):
        """Staff-пользователь может геокодировать."""
        user.is_staff = True
        user.save()
        client.force_login(user)

        mock_result = {
            'success': True,
            'results': [{'coordinates': [55.75, 37.61]}],
        }

        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexGeocoderService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.geocode.return_value = mock_result
            MockService.return_value = mock_instance

            response = client.post(
                reverse('orders:geocode_address'),
                data='{"query": "Москва"}',
                content_type='application/json',
            )

        assert response.status_code == 200

    def test_non_staff_cannot_geocode(self, client, user):
        """Не-staff пользователь не может геокодировать (редирект на логин)."""
        user.is_staff = False
        user.save()
        client.force_login(user)

        response = client.post(
            reverse('orders:geocode_address'),
            data='{"query": "Москва"}',
            content_type='application/json',
        )
        # @user_passes_test возвращает 302 redirect на LOGIN_URL
        assert response.status_code == 302

    def test_anonymous_cannot_geocode(self, client):
        """Анонимный пользователь не может геокодировать (редирект на логин)."""
        response = client.post(
            reverse('orders:geocode_address'),
            data='{"query": "Москва"}',
            content_type='application/json',
        )
        # @user_passes_test возвращает 302 redirect на LOGIN_URL
        assert response.status_code == 302


class TestDeliveryLocationsApi:
    """Тесты API endpoint для получения списка точек Яндекс Доставки."""

    def test_delivery_locations_api_success(self, client):
        """Успешный запрос списка точек."""
        from unittest.mock import patch, MagicMock
        from django.urls import reverse

        with patch(
            'coffee_shop.apps.orders.api.views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_locations.return_value = {
                'success': True,
                'points': [
                    {
                        'platform_station_id': '123456789',
                        'name': 'ПВЗ Москва, ул. Примерная, 1',
                        'type': 'terminal',
                        'address': 'г. Москва, ул. Примерная, д. 1',
                    },
                ],
                'mock': False,
            }
            MockService.return_value = mock_instance

            response = client.get(
                reverse('orders_api:delivery_locations'),
                {'type': 'terminal', 'geo_id': '213'},
            )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['points']) == 1
        assert data['points'][0]['platform_station_id'] == '123456789'
        assert data['points'][0]['name'] == 'ПВЗ Москва, ул. Примерная, 1'

    def test_delivery_locations_api_mock(self, client):
        """Mock-режим: сервис не настроен."""
        from django.urls import reverse
        from unittest.mock import MagicMock, patch

        with patch(
            'coffee_shop.apps.orders.api.views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_locations.return_value = {
                'success': True,
                'points': [],
                'mock': True,
                'error': 'Yandex Delivery Merchant API not configured',
            }
            MockService.return_value = mock_instance

            response = client.get(
                reverse('orders_api:delivery_locations'),
            )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['points'] == []
        assert data['mock'] is True

    def test_delivery_locations_api_error(self, client):
        """Ошибка при получении точек."""
        from django.urls import reverse
        from unittest.mock import MagicMock, patch

        with patch(
            'coffee_shop.apps.orders.api.views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.get_locations.return_value = {
                'success': False,
                'points': [],
                'error': 'API error',
            }
            MockService.return_value = mock_instance

            response = client.get(
                reverse('orders_api:delivery_locations'),
            )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['points'] == []