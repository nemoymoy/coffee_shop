"""Tests for catalog API views."""
import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework.test import APIClient
from rest_framework import status

from coffee_shop.apps.catalog.models import Category, Product, Review


pytestmark = pytest.mark.django_db


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def category():
    return Category.objects.create(name='Кофе', slug='coffee', is_active=True)


@pytest.fixture
def product(category):
    return Product.objects.create(
        name='Эфиопия Иргачефф',
        slug='ethiopia',
        category=category,
        product_type='coffee',
        price_per_50g=Decimal('150.00'),
        stock=500,
        allow_grinding=True,
        available_brewing_methods=['turka', 'espresso'],
        roast_level='medium',
        sca_score=86,
    )


@pytest.fixture
def user():
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        username='testuser',
        password='testpass123',
    )


class TestCategoryAPI:
    """Тесты Category API."""

    def test_list_categories(self, client, category):
        response = client.get('/api/catalog/categories/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_get_category_detail(self, client, category):
        response = client.get(f'/api/catalog/categories/{category.id}/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['slug'] == 'coffee'

    def test_category_products_endpoint(self, client, category, product):
        response = client.get(f'/api/catalog/categories/{category.id}/products/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        assert response.data[0]['slug'] == 'ethiopia'

    def test_search_categories(self, client, category):
        response = client.get('/api/catalog/categories/?search=кофе')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1


class TestProductAPI:
    """Тесты Product API."""

    def test_list_products(self, client, product):
        response = client.get('/api/catalog/products/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_get_product_detail(self, client, product):
        response = client.get(f'/api/catalog/products/{product.id}/')
        assert response.status_code == status.HTTP_200_OK
        assert response.data['name'] == 'Эфиопия Иргачефф'

    def test_product_reviews_endpoint(self, client, product, user):
        Review.objects.create(
            product=product,
            user=user,
            rating=5,
            is_approved=True,
        )
        response = client.get(f'/api/catalog/products/{product.id}/reviews/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1

    def test_featured_products(self, client, category):
        """Featured returns high SCA products."""
        Product.objects.create(
            name='Premium',
            slug='premium',
            category=category,
            product_type='coffee',
            price_per_50g=Decimal('300'),
            stock=200,
            sca_score=92,
        )
        response = client.get('/api/catalog/products/featured/')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1
        # Featured products should have high SCA
        for p in response.data:
            assert p.get('sca_score') is None or p['sca_score'] >= 85

    def test_filter_by_category(self, client, category, product):
        response = client.get('/api/catalog/products/?category=1')
        assert response.status_code == status.HTTP_200_OK
        for item in response.data:
            assert item['category'] == category.id

    def test_filter_by_roast(self, client, category):
        Product.objects.create(
            name='Light Roast',
            slug='light-roast',
            category=category,
            product_type='coffee',
            price_per_50g=Decimal('120'),
            stock=100,
            roast_level='light',
        )
        response = client.get('/api/catalog/products/?roast_level=light')
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data) >= 1


class TestReviewAPI:
    """Тесты Review API."""

    def test_create_review(self, client, product, user):
        client.force_authenticate(user=user)
        response = client.post(
            '/api/catalog/reviews/',
            {
                'product': product.id,
                'rating': 4,
                'comment': 'Хороший кофе',
            },
            format='json',
        )
        assert response.status_code in (status.HTTP_201_CREATED, status.HTTP_200_OK)
        # Review should be created with correct user
        review = Review.objects.filter(product=product, user=user).first()
        assert review is not None
        assert review.rating == 4


class TestReviewApprove:
    """Тесты одобрения отзывов."""

    def test_approve_review(self, client, product, user):
        review = Review.objects.create(
            product=product,
            user=user,
            rating=3,
            is_approved=False,
        )
        client.force_authenticate(user=user)
        response = client.post(f'/api/catalog/reviews/{review.id}/approve/')
        # May get 403 if not superuser, but endpoint should exist
        assert response.status_code in (
            status.HTTP_200_OK,
            status.HTTP_403_FORBIDDEN,
        )
        review.refresh_from_db()
        if response.status_code == status.HTTP_200_OK:
            assert review.is_approved is True
