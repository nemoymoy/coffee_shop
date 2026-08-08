"""Tests for stock service (cart control)."""
import pytest
from django.db import transaction
from decimal import Decimal
from coffee_shop.apps.catalog.services import CartService


class TestCartService:
    """Тесты корзины и контроля остатков."""

    def test_create_order_item_coffee(self, coffee_beans):
        """Создание позиции кофе с списанием остатка."""
        from coffee_shop.apps.orders.models import Order
        order = Order.objects.create(
            status='new',
            total_amount=Decimal('300.00'),
            payment_method='online',
            delivery_method='pickup',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com'
        )
        initial_stock = coffee_beans.stock

        CartService.create_order_item(order, coffee_beans, 200, 'beans', None)

        coffee_beans.refresh_from_db()
        assert coffee_beans.stock == initial_stock - 200
        assert order.items.count() == 1
        item = order.items.first()
        assert item.coffee_weight_grams == 200
        assert item.coffee_form == 'beans'

    def test_create_order_item_exceeds_stock(self, coffee_beans):
        """Попытка заказать больше, чем есть на складе."""
        from coffee_shop.apps.orders.models import Order
        order = Order.objects.create(
            status='new',
            total_amount=Decimal('100.00'),
            payment_method='online',
            delivery_method='pickup',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com'
        )
        with pytest.raises(ValueError, match='только 1000'):
            CartService.create_order_item(order, coffee_beans, 1001, 'beans', None)

        # Остаток не должен измениться
        coffee_beans.refresh_from_db()
        assert coffee_beans.stock == 1000

    def test_create_order_item_non_coffee(self, cake):
        """Создание позиции не-кофе товара."""
        from coffee_shop.apps.orders.models import Order
        order = Order.objects.create(
            status='new',
            total_amount=Decimal('350.00'),
            payment_method='online',
            delivery_method='pickup',
            first_name='Иван',
            last_name='Иванов',
            phone='+79991234567',
            email='test@example.com'
        )
        CartService.create_order_item(order, cake, 1, 'beans', None)
        cake.refresh_from_db()
        assert cake.stock == 19

    def test_cart_item_data_coffee(self, coffee_beans):
        """Данные корзины для кофе."""
        data = CartService.get_cart_item_data(
            coffee_beans, 200, 'ground', 'turka'
        )
        assert data['quantity'] == 1
        assert data['unit_price'] == Decimal('600.00')  # 200/50 * 150
        assert data['coffee_weight_grams'] == 200
        assert data['coffee_form'] == 'ground'
        assert data['brewing_method'] == 'turka'

    def test_cart_item_data_non_coffee(self, cake):
        """Данные корзины для не-кофе."""
        data = CartService.get_cart_item_data(cake, 1, 'beans', None)
        assert data['unit_price'] == Decimal('350.00')
        assert data['coffee_weight_grams'] is None
