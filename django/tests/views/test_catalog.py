"""Tests for catalog views."""
import pytest
from django.urls import reverse
from coffee_shop.apps.catalog.models import Category, Product


pytestmark = pytest.mark.django_db


class TestCatalogView:
    """Тесты представления каталога."""

    def test_catalog_page_loads(self, client):
        Category.objects.create(name='Кофе', slug='coffee')
        response = client.get(reverse('catalog:catalog'))
        assert response.status_code == 200

    def test_catalog_with_products(self, client):
        category = Category.objects.create(name='Кофе', slug='coffee')
        Product.objects.create(
            name='Test Coffee',
            slug='test-coffee',
            category=category,
            product_type='coffee',
            price_per_50g=500,
            is_available=True,
            is_active=True,
        )
        response = client.get(reverse('catalog:catalog'))
        assert response.status_code == 200

    def test_catalog_filters_by_category(self, client):
        cat1 = Category.objects.create(name='Кофе', slug='coffee')
        cat2 = Category.objects.create(name='Чай', slug='tea')
        Product.objects.create(
            name='Coffee 1',
            slug='coffee-1',
            category=cat1,
            product_type='coffee',
            price_per_50g=500,
            is_available=True,
            is_active=True,
        )
        Product.objects.create(
            name='Tea 1',
            slug='tea-1',
            category=cat2,
            product_type='other',
            base_price=300,
            is_available=True,
            is_active=True,
        )
        response = client.get(f'{reverse("catalog:catalog")}?category=coffee')
        assert response.status_code == 200

    def test_product_detail_page(self, client):
        Product.objects.create(
            name='Detail Test',
            slug='detail-test',
            product_type='coffee',
            price_per_50g=500,
            stock=500,
            is_available=True,
            is_active=True,
        )
        response = client.get(reverse('catalog:product_detail', args=['detail-test']))
        assert response.status_code == 200

    def test_product_detail_not_found(self, client):
        response = client.get(reverse('catalog:product_detail', args=['non-existent']))
        assert response.status_code == 404

    def test_home_page(self, client):
        response = client.get(reverse('catalog:home'))
        assert response.status_code == 200

    def test_about_page(self, client):
        response = client.get(reverse('catalog:about'))
        assert response.status_code == 200

    def test_unavailable_products_hidden(self, client):
        Product.objects.create(
            name='Hidden',
            slug='hidden',
            product_type='coffee',
            price_per_50g=500,
            is_available=False,
            is_active=True,
        )
        response = client.get(reverse('catalog:catalog'))
        assert b'Hidden' not in response.content
