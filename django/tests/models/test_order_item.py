"""Tests for OrderItem model."""
import pytest
from django.core.exceptions import ValidationError
from coffee_shop.apps.orders.models import OrderItem
from coffee_shop.apps.catalog.models import Product


pytestmark = pytest.mark.django_db


class TestOrderItem:
    """Тесты модели OrderItem."""

    @pytest.fixture
    def coffee_product(self):
        return Product.objects.create(
            name='Test Coffee',
            slug='test-coffee',
            product_type='coffee',
            price_per_50g=500,
            stock=500,
        )

    def test_create_order_item(self, order, coffee_product):
        item = OrderItem.objects.create(
            order=order,
            product=coffee_product,
            quantity=1,
            unit_price=500,
            coffee_weight_grams=100,
            coffee_form='beans',
        )
        assert item.quantity == 1
        assert item.total_price == 500

    def test_total_price(self, order, coffee_product):
        item = OrderItem.objects.create(
            order=order,
            product=coffee_product,
            quantity=3,
            unit_price=100,
        )
        assert item.total_price == 300

    def test_coffee_form_beans(self, order, coffee_product):
        item = OrderItem.objects.create(
            order=order,
            product=coffee_product,
            quantity=1,
            unit_price=500,
            coffee_weight_grams=200,
            coffee_form='beans',
            brewing_method=None,
        )
        assert item.coffee_form == OrderItem.COFFEE_FORM_BEANS
        assert item.brewing_method is None

    def test_coffee_form_ground(self, order, coffee_product):
        item = OrderItem.objects.create(
            order=order,
            product=coffee_product,
            quantity=1,
            unit_price=500,
            coffee_weight_grams=100,
            coffee_form='ground',
            brewing_method='espresso',
        )
        assert item.coffee_form == OrderItem.COFFEE_FORM_GROUND
        assert item.brewing_method == 'espresso'

    def test_order_cascade_delete(self, order, coffee_product):
        item = OrderItem.objects.create(
            order=order,
            product=coffee_product,
            quantity=1,
            unit_price=500,
        )
        order.delete()
        assert not OrderItem.objects.filter(pk=item.pk).exists()

    def test_str(self, order, coffee_product):
        item = OrderItem.objects.create(
            order=order,
            product=coffee_product,
            quantity=2,
            unit_price=100,
        )
        assert str(item) == 'Test Coffee x2'
