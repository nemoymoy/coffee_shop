"""Tests for checkout views."""
import pytest
from django.urls import reverse
from coffee_shop.apps.catalog.models import Category, Product


pytestmark = pytest.mark.django_db


class TestCheckoutView:
    """Тесты оформления заказа."""

    def test_checkout_with_empty_cart(self, client):
        response = client.get(reverse('orders:checkout'))
        assert response.status_code == 302  # redirect

    def test_checkout_with_items(self, client):
        # Создаём кофе
        category = Category.objects.create(name='Кофе', slug='coffee')
        product = Product.objects.create(
            name='Test Coffee',
            slug='test-coffee',
            category=category,
            product_type='coffee',
            price_per_50g=500,
            stock=500,
            is_available=True,
            is_active=True,
        )

        # Добавляем в сессию через POST
        response = client.post(
            reverse('orders:cart_add'),
            {
                'product_id': product.pk,
                'weight': 100,
                'coffee_form': 'beans',
                'brewing_method': None,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert response.status_code == 200

        # Теперь checkout должен работать
        response = client.get(reverse('orders:checkout'))
        assert response.status_code == 200

    def test_checkout_form_submit(self, client):
        category = Category.objects.create(name='Кофе', slug='coffee')
        product = Product.objects.create(
            name='Test Coffee',
            slug='test-coffee',
            category=category,
            product_type='coffee',
            price_per_50g=500,
            stock=1000,
            is_available=True,
            is_active=True,
        )

        # Add item to session cart
        response = client.post(
            reverse('orders:cart_add'),
            {
                'product_id': product.pk,
                'weight': 100,
                'coffee_form': 'beans',
                'brewing_method': None,
            },
            HTTP_X_REQUESTED_WITH='XMLHttpRequest',
        )
        assert response.status_code == 200

        # POST order
        response = client.post(
            reverse('orders:checkout'),
            {
                'first_name': 'Иван',
                'last_name': 'Иванов',
                'phone': '+7 (999) 123-45-67',
                'email': 'ivan@example.com',
                'delivery_method': 'pickup',
                'payment_method': 'online',
                'delivery_address': '',
                'comment': 'Быстрее доставьте!',
            },
            follow=True,
        )
        assert response.status_code == 200

    def test_checkout_post_too_many_requests(self, client):
        """Тест rate limiting."""
        category = Category.objects.create(name='Кофе', slug='coffee')
        product = Product.objects.create(
            name='Test Coffee',
            slug='test-coffee',
            category=category,
            product_type='coffee',
            price_per_50g=500,
            stock=500,
            is_available=True,
            is_active=True,
        )

        # Отправляем 30 запросов + 1
        for i in range(31):
            response = client.post(
                reverse('orders:cart_add'),
                {
                    'product_id': product.pk,
                    'weight': 50,
                    'coffee_form': 'beans',
                    'brewing_method': None,
                },
                HTTP_X_REQUESTED_WITH='XMLHttpRequest',
            )
            if i >= 29:
                assert response.status_code == 429

    def test_health_check(self, client):
        response = client.get('/health/')
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ok'
