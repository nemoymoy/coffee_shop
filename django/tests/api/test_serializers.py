"""Tests for catalog serializers."""
import pytest
from decimal import Decimal

from coffee_shop.apps.catalog.models import Category, Product, Review
from coffee_shop.apps.catalog.serializers import (
    CategorySerializer,
    ProductSerializer,
    ReviewSerializer,
)


pytestmark = pytest.mark.django_db


@pytest.fixture
def category():
    return Category.objects.create(name='Кофе', slug='coffee', is_active=True)


@pytest.fixture
def sub_category(category):
    return Category.objects.create(
        name='Зерновой',
        slug='beans',
        parent=category,
        is_active=True,
    )


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
        coffee_type='Арабика',
        roast_level='medium',
        origin_region='Эфиопия',
        processing_method='washed',
        sca_score=86,
    )


@pytest.fixture
def user():
    from django.contrib.auth import get_user_model
    User = get_user_model()
    return User.objects.create_user(
        username='testuser',
        password='testpass123',
        first_name='Тест',
        last_name='Пользователь',
    )


class TestCategorySerializer:
    """Тесты CategorySerializer."""

    def test_basic_fields(self, category):
        data = CategorySerializer(category).data
        assert data['id'] == category.id
        assert data['name'] == 'Кофе'
        assert data['slug'] == 'coffee'
        assert data['is_active'] is True

    def test_children(self, category, sub_category):
        data = CategorySerializer(category).data
        assert len(data['children']) == 1
        assert data['children'][0]['slug'] == 'beans'

    def test_product_count(self, category, product):
        data = CategorySerializer(category).data
        assert data['product_count'] == 1

    def test_inactive_not_counted(self, category):
        product = Product.objects.create(
            name='Скрытый',
            slug='hidden',
            category=category,
            is_available=False,
            product_type='coffee',
            price_per_50g=100,
        )
        data = CategorySerializer(category).data
        assert data['product_count'] == 0

    def test_inactive_child_not_shown(self, category):
        inactive = Category.objects.create(
            name='Скрытая',
            slug='hidden-cat',
            parent=category,
            is_active=False,
        )
        data = CategorySerializer(category).data
        assert len(data['children']) == 0


class TestProductSerializer:
    """Тесты ProductSerializer."""

    def test_basic_fields(self, product):
        data = ProductSerializer(product).data
        assert data['name'] == 'Эфиопия Иргачефф'
        assert data['category_name'] == 'Кофе'
        assert data['product_type'] == 'coffee'
        assert data['sca_score'] == 86

    def test_review_count_zero(self, product):
        data = ProductSerializer(product).data
        assert data['review_count'] == 0
        assert data['average_rating'] is None

    def test_review_count_with_approved(self, product, user):
        Review.objects.create(
            product=product,
            user=user,
            rating=5,
            is_approved=True,
        )
        Review.objects.create(
            product=product,
            user=user,
            rating=3,
            is_approved=True,
        )
        data = ProductSerializer(product).data
        assert data['review_count'] == 2
        assert data['average_rating'] == 4.0

    def test_review_unapproved_not_counted(self, product, user):
        Review.objects.create(
            product=product,
            user=user,
            rating=1,
            is_approved=False,
        )
        data = ProductSerializer(product).data
        assert data['review_count'] == 0


class TestReviewSerializer:
    """Тесты ReviewSerializer."""

    def test_basic_fields(self, product, user):
        review = Review.objects.create(
            product=product,
            user=user,
            rating=5,
            comment='Отличный кофе!',
            is_approved=True,
        )
        data = ReviewSerializer(review).data
        assert data['rating'] == 5
        assert data['comment'] == 'Отличный кофе!'
        assert data['username'] == 'testuser'
        assert data['user_name'] == 'Тест Пользователь'

    def test_create_with_request(self, product, user, rf):
        """Создание отзыва через serializer с request."""
        from django.contrib.auth.models import AnonymousUser
        request = rf.post('/')
        request.user = user
        serializer = ReviewSerializer(
            data={
                'product': product.pk,
                'rating': 4,
                'comment': 'Хорошо',
            },
            context={'request': request},
        )
        assert serializer.is_valid()
        review = serializer.save()
        assert review.user == user
