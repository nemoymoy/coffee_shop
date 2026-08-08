"""Tests for Order and OrderItem models."""
import pytest
from decimal import Decimal

from coffee_shop.apps.orders.models import Order, OrderItem


class TestOrderModel:
    """Тесты модели Order."""

    def test_create_order(self, user):
        order = Order.objects.create(
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

        assert order.pk is not None
        assert str(order) == 'Заказ #{} — Иванов Иван'.format(order.pk)
        assert order.status == 'new'

    def test_order_no_user(self):
        """Анонимный заказ."""
        order = Order.objects.create(
            status='new',
            total_amount=Decimal('300.00'),
            payment_method='cash',
            delivery_method='delivery',
            first_name='Гость',
            last_name='',
            phone='+79990000000',
            email='guest@test.com',
            delivery_address='ул. Тестовая, 1'
        )

        assert order.user is None
        assert order.delivery_method == 'delivery'

    def test_order_status_choices(self):
        """Все статусы заказа."""
        statuses = [s[0] for s in Order.STATUS_CHOICES]
        assert 'new' in statuses
        assert 'in_progress' in statuses
        assert 'ready' in statuses
        assert 'delivered' in statuses
        assert 'cancelled' in statuses

    def test_order_items_relation(self, order, order_item):
        """Связь Order.items."""
        assert order.items.count() == 1
        assert order.items.first() == order_item


class TestOrderItemModel:
    """Тесты модели OrderItem."""

    def test_create_order_item_beans(self, coffee_beans, order):
        """Позиция с кофе в зёрнах."""
        item = OrderItem.objects.create(
            order=order,
            product=coffee_beans,
            quantity=1,
            unit_price=Decimal('300.00'),
            coffee_weight_grams=200,
            coffee_form='beans',
            brewing_method=None
        )

        assert item.coffee_weight_grams == 200
        assert item.coffee_form == 'beans'
        assert item.brewing_method is None
        assert item.total_price == Decimal('300.00')

    def test_create_order_item_ground(self, coffee_beans, order):
        """Позиция с молотым кофе."""
        item = OrderItem.objects.create(
            order=order,
            product=coffee_beans,
            quantity=1,
            unit_price=Decimal('450.00'),
            coffee_weight_grams=300,
            coffee_form='ground',
            brewing_method='turka'
        )

        assert item.coffee_form == 'ground'
        assert item.brewing_method == 'turka'
        assert item.total_price == Decimal('450.00')

    def test_create_order_item_total(self):
        """Расчёт итоговой цены позиции."""
        item = OrderItem(
            quantity=3,
            unit_price=Decimal('100.00')
        )
        assert item.total_price == Decimal('300.00')


class TestPromoCodeModel:
    """Тесты модели PromoCode."""

    def test_promo_code_valid(self, promo_code):
        """Промокод валиден."""
        assert promo_code.is_valid is True
        assert promo_code.is_active is True

    def test_promo_code_remaining_uses(self, promo_code):
        """Оставшиеся использования."""
        assert promo_code.remaining_uses == 99  # 100 - 1
        promo_code.used_count = 100
        promo_code.save()
        assert promo_code.remaining_uses == 0

    def test_promo_code_unlimited(self):
        """Безлимитный промокод."""
        from django.utils import timezone
        from datetime import timedelta

        pc = PromoCode.objects.create(
            code='UNLIMITED',
            discount_type='percent',
            discount_value=5,
            max_uses=0,
            valid_from=timezone.now() - timedelta(days=1),
            valid_to=timezone.now() + timedelta(days=30),
            is_active=True
        )

        assert pc.remaining_uses == 0  # 0 означает безлимит
        assert pc.is_valid is True
