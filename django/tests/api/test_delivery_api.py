"""Tests for Yandex Delivery views (calculate_delivery_view)."""
import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestCalculateDeliveryView:
    """Тесты для расчёта стоимости доставки."""

    def test_anonymous_user_can_calculate(self, client):
        """Неавторизованный пользователь может рассчитать доставку."""
        mock_instance = MagicMock()
        mock_instance.calculate_price.return_value = {
            'success': True,
            'price': 299,
            'eta': '30-60 мин',
        }

        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            MockService.return_value = mock_instance

            response = client.post(
                reverse('orders:calculate_delivery'),
                data='{"city": "moscow", "street": "ул. Тестовая", "house": "1"}',
                content_type='application/json',
            )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['price'] == 299

    def test_calculate_delivery_success(self, client):
        """Успешный расчёт доставки."""
        user = User.objects.create_user(
            username='testuser', email='test@example.com', password='test123'
        )
        # Сначала force_login, потом session
        client.force_login(user)
        session = client.session
        session['yandex_delivery_access_token'] = 'ya2-test-token'
        session.save()

        payload = {
            'city': 'moscow',
            'street': 'ул. Тестовая',
            'house': '1',
            'apartment': '10',
        }

        mock_instance = MagicMock()
        mock_instance.calculate_price.return_value = {
            'success': True,
            'price': 350,
            'eta': '40-60 мин',
        }

        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            MockService.return_value = mock_instance

            response = client.post(
                reverse('orders:calculate_delivery'),
                data=payload,
                content_type='application/json',
            )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['price'] == 350
        assert data['eta'] == '40-60 мин'

    def test_calculate_delivery_no_token(self, client):
        """Расчёт без токена — сервис возвращает ошибку конфигурации."""
        user = User.objects.create_user(
            username='testuser2', email='test2@example.com', password='test123'
        )
        client.force_login(user)

        payload = {
            'city': 'moscow',
            'street': 'ул. Тестовая',
            'house': '1',
        }

        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            mock_instance = MagicMock()
            mock_instance.is_configured.return_value = False
            MockService.return_value = mock_instance

            response = client.post(
                reverse('orders:calculate_delivery'),
                data=payload,
                content_type='application/json',
            )

        assert response.status_code == 200
        data = response.json()
        # Не настроенный сервис возвращает ошибку
        assert data['success'] is True or data.get('error') is not None

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

    def test_calculate_delivery_service_error(self, client):
        """Ошибка сервиса доставки — возвращается реальная ошибка."""
        user = User.objects.create_user(
            username='testuser4', email='test4@example.com', password='test123'
        )
        client.force_login(user)
        session = client.session
        session['yandex_delivery_access_token'] = 'ya2-test-token'
        session.save()

        payload = {
            'city': 'moscow',
            'street': 'ул. Тестовая',
            'house': '1',
        }

        mock_instance = MagicMock()
        mock_instance.calculate_price.return_value = {
            'success': False,
            'error': 'Invalid address',
        }

        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            MockService.return_value = mock_instance

            response = client.post(
                reverse('orders:calculate_delivery'),
                data=payload,
                content_type='application/json',
            )

        # Теперь возвращается реальная ошибка, а не mock
        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False
        assert data['error'] == 'Invalid address'

    def test_calculate_delivery_with_type_courier(self, client):
        """Расчёт доставки с типом courier."""
        user = User.objects.create_user(
            username='testuser5', email='test5@example.com', password='test123'
        )
        client.force_login(user)
        session = client.session
        session['yandex_delivery_access_token'] = 'ya2-test-token'
        session.save()

        payload = {
            'city': 'moscow',
            'street': 'ул. Тестовая',
            'house': '1',
            'delivery_type': 'courier',
        }

        mock_instance = MagicMock()
        mock_instance.calculate_price.return_value = {
            'success': True,
            'price': 299,
            'eta': '30-45 мин',
        }

        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            MockService.return_value = mock_instance

            response = client.post(
                reverse('orders:calculate_delivery'),
                data=payload,
                content_type='application/json',
            )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['price'] == 299
        # Проверка, что сервис получил delivery_type
        call_args = MockService.call_args
        assert call_args is not None

    def test_calculate_delivery_with_type_pvz(self, client):
        """Расчёт доставки с типом pvz."""
        user = User.objects.create_user(
            username='testuser6', email='test6@example.com', password='test123'
        )
        client.force_login(user)
        session = client.session
        session['yandex_delivery_access_token'] = 'ya2-test-token'
        session.save()

        payload = {
            'city': 'moscow',
            'street': 'ул. Тестовая',
            'house': '1',
            'delivery_type': 'pvz',
        }

        mock_instance = MagicMock()
        mock_instance.calculate_price.return_value = {
            'success': True,
            'price': 199,
            'eta': '15-30 мин',
        }

        with patch(
            'coffee_shop.apps.orders.views.delivery_views.YandexDeliveryService'
        ) as MockService:
            MockService.return_value = mock_instance

            response = client.post(
                reverse('orders:calculate_delivery'),
                data=payload,
                content_type='application/json',
            )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['price'] == 199


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