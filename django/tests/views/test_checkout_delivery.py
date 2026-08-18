"""Tests for checkout with Yandex Delivery integration."""
import pytest
from unittest.mock import patch, MagicMock
from django.urls import reverse
from django.contrib.auth import get_user_model
from coffee_shop.apps.orders.models import Order

User = get_user_model()

pytestmark = pytest.mark.django_db(transaction=True)


class TestCheckoutWithDelivery:
    """Тесты оформления заказа с доставкой."""

    def _setup_session(self, client, coffee_beans, token=None):
        """Устанавливает cart и token в сессию client."""
        # Создаём сессию и сохраняем данные
        session = client.session
        session['cart'] = {
            f"{coffee_beans.id}:200:beans:espresso": {
                'product_id': coffee_beans.id,
                'weight': '200',
                'coffee_form': 'beans',
                'brewing_method': 'espresso',
                'price': 600.0,
                'quantity': 1,
            }
        }
        if token:
            session['yandex_delivery_access_token'] = token
            session['yandex_delivery_refresh_token'] = 'refresh-test-token'
        session.save()

    def test_checkout_with_delivery_creates_yandex_order(
        self, client, coffee_beans
    ):
        """Checkout с доставкой создаёт заказ в Яндекс."""
        self._setup_session(client, coffee_beans, token='ya2-test-token')

        payload = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'test@example.com',
            'delivery_method': 'delivery',
            'payment_method': 'online',
            'delivery_address': 'Москва, ул. Тестовая, 1, 10',
            'comment': 'Быстрее',
        }

        mock_instance = MagicMock()
        mock_instance.create_delivery_order.return_value = {
            'success': True,
            'yandex_order_id': 'YDO-12345',
            'tracking_number': 'YA-TRACK-001',
            'price': 299,
        }

        with patch(
            'coffee_shop.apps.orders.order_views.YandexDeliveryService'
        ) as MockService:
            MockService.return_value = mock_instance

            response = client.post(
                reverse('orders:checkout'),
                data=payload,
            )

        assert response.status_code in (200, 302)
        assert Order.objects.count() == 1
        order = Order.objects.first()

        assert order.yandex_order_id == 'YDO-12345'
        assert order.tracking_number == 'YA-TRACK-001'
        assert order.delivery_status == 'pending'
        assert order.delivery_cost == 299
        assert order.delivery_method == 'delivery'

    def test_checkout_with_delivery_no_token(self, client, coffee_beans):
        """Checkout с доставкой без токена — Yandex не создаётся."""
        # Устанавливаем cart напрямую в сессию
        session = client.session
        session['cart'] = {
            f"{coffee_beans.id}:200:beans:espresso": {
                'product_id': coffee_beans.id,
                'weight': '200',
                'coffee_form': 'beans',
                'brewing_method': 'espresso',
                'price': 600.0,
                'quantity': 1,
            }
        }
        session.save()

        payload = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'test@example.com',
            'delivery_method': 'delivery',
            'payment_method': 'online',
            'delivery_address': 'Москва, ул. Тестовая, 1, 10',
        }

        with patch(
            'coffee_shop.apps.orders.order_views.YandexDeliveryService'
        ) as MockService:
            MockService.return_value = MagicMock()

            response = client.post(
                reverse('orders:checkout'),
                data=payload,
            )

        assert response.status_code in (200, 302)
        assert Order.objects.count() == 1
        order = Order.objects.first()
        assert order.yandex_order_id is None
        assert order.status == 'new'
        MockService.assert_not_called()

    def test_checkout_with_delivery_service_error(self, client, coffee_beans):
        """Ошибка Yandex — заказ всё равно создаётся."""
        self._setup_session(client, coffee_beans, token='ya2-test-token')

        payload = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'test@example.com',
            'delivery_method': 'delivery',
            'payment_method': 'online',
            'delivery_address': 'Москва, ул. Тестовая, 1, 10',
        }

        mock_instance = MagicMock()
        mock_instance.create_delivery_order.return_value = {
            'success': False,
            'error': 'Service unavailable',
        }

        with patch(
            'coffee_shop.apps.orders.order_views.YandexDeliveryService'
        ) as MockService:
            MockService.return_value = mock_instance

            response = client.post(
                reverse('orders:checkout'),
                data=payload,
            )

        assert Order.objects.count() == 1
        order = Order.objects.first()
        assert order.yandex_order_id is None
