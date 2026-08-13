import sys
import os

# Add django directory to Python path before any Django imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'django')))

import pytest
from decimal import Decimal
from django.contrib.auth.models import User

from coffee_shop.apps.catalog.models import Category, Product
from coffee_shop.apps.orders.models import Order, OrderItem, PromoCode


# ====== Category Fixtures ======

@pytest.mark.django_db
@pytest.fixture
def category():
    """Базовая категория."""
    return Category.objects.create(
        name='Кофе',
        slug='coffee',
        is_active=True
    )


@pytest.mark.django_db
@pytest.fixture
def category_desserts():
    """Категория десертов."""
    return Category.objects.create(
        name='Десерты',
        slug='desserts',
        is_active=True
    )


# ====== Product Fixtures ======

@pytest.mark.django_db
@pytest.fixture
def coffee_beans(category):
    """Товар: кофе в зёрнах."""
    return Product.objects.create(
        name='Эфиопия Иргачефф',
        slug='ethiopia-irgacheff',
        description='Яркий цветочный аромат с нотами ягод и цитрусовых',
        category=category,
        product_type='coffee',
        price_per_50g=Decimal('150.00'),
        stock=1000,
        is_available=True,
        allow_grinding=True,
        available_brewing_methods=['turka', 'espresso', 'geyser', 'pourover', 'french_press'],
        coffee_type='Арабика 100%',
        roast_level='medium',
        origin_region='Эфиопия, Иргачефф',
        processing_method='washed',
        sca_score=86,
        tasting_notes='Цветочный аромат, ноты черники, лимон, чайное тело, яркая кислотность'
    )


@pytest.mark.django_db
@pytest.fixture
def coffee_ground(category):
    """Товар: кофе молотый."""
    return Product.objects.create(
        name='Бразилия Сантос',
        slug='brazil-santos',
        description='Шоколадный вкус с ореховыми нотами',
        category=category,
        product_type='coffee',
        price_per_50g=Decimal('120.00'),
        stock=500,
        is_available=True,
        allow_grinding=True,
        available_brewing_methods=['espresso', 'geyser', 'french_press', 'filter_machine'],
        coffee_type='Арабика',
        roast_level='dark',
        origin_region='Бразилия, Сантос',
        processing_method='natural',
        sca_score=83,
        tasting_notes='Шоколад, орехи, карамель, среднее тело, мягкая кислотность'
    )


@pytest.mark.django_db
@pytest.fixture
def cake(category_desserts):
    """Товар: не кофе (десерт)."""
    return Product.objects.create(
        name='Чизкейк Нью-Йорк',
        slug='cheesecake-ny',
        description='Классический чизкейк',
        category=category_desserts,
        product_type='other',
        base_price=Decimal('350.00'),
        price_per_50g=Decimal('350.00'),
        stock=20,
        is_available=True
    )


# ====== Order Fixtures ======

@pytest.mark.django_db
@pytest.fixture
def user():
    """Тестовый пользователь."""
    return User.objects.create_user(
        username='testuser',
        email='test@example.com',
        password='testpass123',
        first_name='Иван',
        last_name='Иванов'
    )


@pytest.mark.django_db
@pytest.fixture
def order(coffee_beans, user):
    """Тестовый заказ."""
    o = Order.objects.create(
        user=user,
        status='new',
        total_amount=Decimal('300.00'),
        payment_method='online',
        delivery_method='pickup',
        first_name='Иван',
        last_name='Иванов',
        phone='+79991234567',
        email='test@example.com'
    )
    return o


@pytest.mark.django_db
@pytest.fixture
def order_item(order, coffee_beans):
    """Тестовая позиция заказа."""
    return OrderItem.objects.create(
        order=order,
        product=coffee_beans,
        quantity=1,
        unit_price=Decimal('300.00'),
        coffee_weight_grams=200,
        coffee_form='beans',
        brewing_method=None
    )


# ====== PromoCode Fixtures ======

@pytest.mark.django_db
@pytest.fixture
def promo_code():
    """Тестовый промокод."""
    from django.utils import timezone
    from datetime import timedelta

    now = timezone.now()
    return PromoCode.objects.create(
        code='COFFEE10',
        discount_type='percent',
        discount_value=Decimal('10'),
        max_uses=100,
        valid_from=now - timedelta(days=1),
        valid_to=now + timedelta(days=30),
        is_active=True
    )


# ====== Helper Fixtures ======

@pytest.fixture
def api_client():
    """Django REST framework API client."""
    from rest_framework.test import APIClient
    return APIClient()
