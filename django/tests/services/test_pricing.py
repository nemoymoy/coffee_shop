"""Tests for coffee pricing service."""
from decimal import Decimal
import pytest

from coffee_shop.apps.catalog.services import coffee_price


class TestCoffeePricing:
    """Тесты расчёта стоимости кофе."""

    def test_price_50g(self):
        """Цена за 50г."""
        result = coffee_price(50, Decimal('150.00'))
        assert result == Decimal('150.00')

    def test_price_100g(self):
        """Цена за 100г = 2 * price_per_50g."""
        result = coffee_price(100, Decimal('150.00'))
        assert result == Decimal('300.00')

    def test_price_150g(self):
        """Цена за 150г = 3 * price_per_50g."""
        result = coffee_price(150, Decimal('150.00'))
        assert result == Decimal('450.00')

    def test_price_250g(self):
        """Цена за 250г."""
        result = coffee_price(250, Decimal('120.00'))
        assert result == Decimal('600.00')

    def test_price_1000g(self):
        """Цена за 1000г."""
        result = coffee_price(1000, Decimal('100.00'))
        assert result == Decimal('2000.00')

    def test_price_zero(self):
        """Цена за 0г = 0."""
        result = coffee_price(0, Decimal('150.00'))
        assert result == Decimal('0.00')

    def test_price_negative(self):
        """Цена за отрицательный вес = 0."""
        result = coffee_price(-50, Decimal('150.00'))
        assert result == Decimal('0.00')

    def test_price_not_divisible_by_50(self):
        """Вес не кратен 50: целые 50-граммовые порции."""
        # 75 // 50 = 1 -> 1 * price_per_50g
        result = coffee_price(75, Decimal('150.00'))
        assert result == Decimal('150.00')

    def test_price_complex(self):
        """Сложный расчёт."""
        result = coffee_price(350, Decimal('99.99'))
        assert result == Decimal('699.93')  # 7 * 99.99
