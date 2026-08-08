"""Tests for CartService."""
import pytest
from decimal import Decimal
from coffee_shop.apps.catalog.services.cart_service import CartService


pytestmark = pytest.mark.django_db


class TestCartService:
    """Тесты CartService."""

    def test_calc_price(self):
        price = CartService._calc_price(100, Decimal('500'))
        assert price == Decimal('1000')

    def test_calc_price_50g(self):
        price = CartService._calc_price(50, Decimal('500'))
        assert price == Decimal('500')

    def test_calc_price_zero(self):
        price = CartService._calc_price(0, Decimal('500'))
        assert price == Decimal('0.00')

    def test_calc_price_150g(self):
        price = CartService._calc_price(150, Decimal('500'))
        assert price == Decimal('1500')

    def test_get_cart_item_data_coffee(self, rf, db):
        from coffee_shop.apps.catalog.models import Product
        product = Product.objects.create(
            name='Test Coffee',
            slug='test',
            product_type='coffee',
            price_per_50g=Decimal('500'),
            stock=500,
        )
        data = CartService.get_cart_item_data(product, 100, 'beans', None)
        assert data['quantity'] == 1
        assert data['unit_price'] == Decimal('1000')
        assert data['coffee_weight_grams'] == 100
        assert data['coffee_form'] == 'beans'

    def test_get_cart_item_data_other(self, rf, db):
        from coffee_shop.apps.catalog.models import Product
        product = Product.objects.create(
            name='Other',
            slug='other',
            product_type='other',
            base_price=Decimal('300'),
        )
        data = CartService.get_cart_item_data(product, 0, None, None)
        assert data['unit_price'] == Decimal('300')
        assert data['coffee_weight_grams'] is None
