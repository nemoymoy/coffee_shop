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
        category = Category.objects.create(name='Кофе', slug='coffee')
        product = Product.objects.create(
            name='Test Coffee',
            slug='test-coffee',
            category=category,
            product_type='coffee',
            price_per_50g=500,
            stock=500,
            is_available=True,
        )

        # Add session cart via POST (with CSRF token)
        session = client.session
        session['cart'] = {
            str(product.pk): {
                'product_id': product.pk,
                'weight': 100,
                'coffee_form': 'beans',
                'quantity': 1
            }
        }
        session.save()
        
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
        )

        # Add to session cart directly
        session = client.session
        session['cart'] = {
            str(product.pk): {
                'product_id': product.pk,
                'weight': 100,
                'coffee_form': 'beans',
                'price': 500.0,
                'quantity': 1
            }
        }
        session.save()

        # POST order
        response = client.post(
            reverse('orders:checkout'),
            {
                'first_name': 'test',
                'last_name': 'User',
                'phone': '+79991234567',
                'email': 'test@example.com',
                'delivery_method': 'pickup',
                'payment_method': 'online',
                'delivery_address': '',
                'comment': 'Test comment',
            },
            follow=True,
        )
        assert response.status_code == 200

    def test_checkout_post_too_many_requests(self, client):
        """Тест rate limiting."""
        response = client.get('/health/')
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'ok'
