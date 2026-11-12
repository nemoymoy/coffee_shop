"""Tests for Yandex Delivery refresh order status endpoint."""
import pytest
from decimal import Decimal

from django.test import Client
from coffee_shop.apps.orders.models import Order

pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return Client()


@pytest.fixture
def logged_in_client(client, user):
    client.login(username=user.username, password='testpass123')
    return client


class TestRefreshOrderStatusView:
    """Tests for manual refresh of Yandex Delivery status."""

    def test_refresh_status_non_delivery_order(self, logged_in_client, user):
        """Cannot refresh status for pickup order (no Yandex delivery)."""
        order = Order.objects.create(
            user=user,
            status=Order.Status.NEW,
            total_amount=Decimal('1000'),
            payment_method=Order.PaymentMethod.CASH,
            delivery_method=Order.DeliveryMethod.PICKUP,
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
        )

        response = logged_in_client.post(
            f'/orders/refresh-status/{order.pk}/',
            {},
            content_type='application/json',
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is False
        assert 'не используется доставка' in data['error']

    def test_refresh_status_order_not_found(self, logged_in_client, user):
        """Returns 404 for non-existent order."""
        response = logged_in_client.post(
            '/orders/refresh-status/99999/',
            {},
            content_type='application/json',
        )

        assert response.status_code == 404

    def test_refresh_status_unauthenticated(self, client, user):
        """Unauthenticated user cannot refresh order status."""
        order = Order.objects.create(
            user=user,
            status=Order.Status.NEW,
            total_amount=Decimal('1000'),
            payment_method=Order.PaymentMethod.CASH,
            delivery_method=Order.DeliveryMethod.DELIVERY,
            delivery_api_type='express',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            express_claim_id='CLAIM-UNAUTH',
        )

        response = client.post(
            f'/orders/refresh-status/{order.pk}/',
            {},
            content_type='application/json',
        )

        assert response.status_code == 302  # Redirect to login

    def test_refresh_status_requires_post(self, logged_in_client, user):
        """GET request is not allowed."""
        order = Order.objects.create(
            user=user,
            status=Order.Status.NEW,
            total_amount=Decimal('1000'),
            payment_method=Order.PaymentMethod.CASH,
            delivery_method=Order.DeliveryMethod.DELIVERY,
            delivery_api_type='express',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com',
            delivery_address='Москва, ул. Тестовая, 1',
            express_claim_id='CLAIM-GET',
        )

        response = logged_in_client.get(
            f'/orders/refresh-status/{order.pk}/',
        )

        assert response.status_code == 405  # Method Not Allowed
