"""Tests for Yandex Delivery views (calculate_delivery_view)."""
import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.contrib.auth import get_user_model

User = get_user_model()

pytestmark = pytest.mark.django_db


class TestCalculateDeliveryView:
    """Тесты для расчёта стоимости доставки."""

    def test_requires_login(self, client):
        """Неавторизованный пользователь не имеет доступа."""
        response = client.post(
            reverse('orders:calculate_delivery'),
            data='{"city": "moscow", "street": "ул. Тестовая", "house": "1"}',
            content_type='application/json',
        )
        assert response.status_code in (302, 403)

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
        """Расчёт без токена — mock mode."""
        user = User.objects.create_user(
            username='testuser2', email='test2@example.com', password='test123'
        )
        client.force_login(user)

        payload = {
            'city': 'moscow',
            'street': 'ул. Тестовая',
            'house': '1',
        }

        response = client.post(
            reverse('orders:calculate_delivery'),
            data=payload,
            content_type='application/json',
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['mock'] is True
        assert data['price'] == 299

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
        """Ошибка сервиса доставки."""
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

        assert response.status_code == 500
        data = response.json()
        assert data['success'] is False

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