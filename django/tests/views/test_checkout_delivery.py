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

    def test_checkout_with_delivery_online_payment_defers_yandex(
        self, client, coffee_beans
    ):
        """Checkout с доставкой и онлайн-оплатой: Яндекс не создаётся сразу, статус awaiting_payment."""
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
            'station_id': '123456789',
            'station_name': 'ПВЗ Тестовый',
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

        # Яндекс Доставка НЕ создаётся при онлайн-оплате — ждёт подтверждения платежа
        assert order.yandex_order_id is None
        assert order.tracking_number is None
        assert order.delivery_status is None
        assert order.status == 'awaiting_payment'
        assert order.delivery_method == 'delivery'
        # При онлайн-оплате YandexDeliveryService вообще не вызывается
        assert not MockService.called

    def test_checkout_with_delivery_online_no_token(self, client, coffee_beans):
        """Checkout с доставкой и онлайн-оплатой без токена — Яндекс не создаётся, статус awaiting_payment."""
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
            'station_id': '123456789',
            'station_name': 'ПВЗ Тестовый',
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
        assert order.status == 'awaiting_payment'
        # При онлайн-оплате YandexDeliveryService не вызывается
        assert not MockService.called

    def test_checkout_with_delivery_online_service_error(self, client, coffee_beans):
        """Онлайн-оплата + доставка — Яндекс не создаётся даже если сервис доступен."""
        self._setup_session(client, coffee_beans, token='ya2-test-token')

        payload = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'test@example.com',
            'delivery_method': 'delivery',
            'payment_method': 'online',
            'delivery_address': 'Москва, ул. Тестовая, 1, 10',
            'station_id': '123456789',
            'station_name': 'ПВЗ Тестовый',
        }

        with patch(
            'coffee_shop.apps.orders.order_views.YandexDeliveryService'
        ) as MockService:
            MockService.return_value = MagicMock()

            response = client.post(
                reverse('orders:checkout'),
                data=payload,
            )

        assert Order.objects.count() == 1
        order = Order.objects.first()
        assert order.yandex_order_id is None
        assert order.status == 'awaiting_payment'


class TestCheckoutWithDeliveryType:
    """Тесты оформления заказа с доставкой и оплатой при получении.
    
    Онлайн-оплата с доставкой проверяется в TestCheckoutWithDelivery.
    Здесь тестируется оплата при получении — Яндекс Доставка создаётся сразу.
    """

    def _setup_session(self, client, coffee_beans):
        """Устанавливает cart в сессию client."""
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

    def test_checkout_cash_payment_creates_yandex_order(self, client, coffee_beans):
        """Checkout с доставкой и оплатой при получении — Яндекс создаётся сразу."""
        self._setup_session(client, coffee_beans)

        payload = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'test@example.com',
            'delivery_method': 'delivery',
            'payment_method': 'cash',
            'delivery_address': 'Москва, ул. Тестовая, 1, 10',
            'comment': 'Быстрее',
            'station_id': '123456789',
            'station_name': 'ПВЗ Тестовый',
        }

        mock_instance = MagicMock()
        mock_instance.create_order.return_value = {
            'success': True,
            'order_id': 'YDO-12345',
            'tracking_number': 'YA-TRACK-001',
        }

        with patch(
            'coffee_shop.apps.orders.order_views.YandexDeliveryService'
        ) as MockService:
            MockService.return_value = mock_instance
            MockService.return_value.is_configured.return_value = True

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
        assert order.status == 'in_progress'
        assert order.delivery_method == 'delivery'
        assert order.payment_method == 'cash'
        mock_instance.create_order.assert_called_once()

    def test_checkout_cash_payment_pickup_no_yandex(self, client, coffee_beans):
        """Checkout с самовывозом — Яндекс Доставка не создаётся."""
        self._setup_session(client, coffee_beans)

        payload = {
            'first_name': 'Иван',
            'last_name': 'Иванов',
            'phone': '+79991234567',
            'email': 'test@example.com',
            'delivery_method': 'pickup',
            'payment_method': 'cash',
            'comment': 'Тест',
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
