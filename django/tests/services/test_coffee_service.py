"""Tests for coffee service validation."""
import pytest

from coffee_shop.apps.catalog.services import CoffeeService
from coffee_shop.apps.orders.models import OrderItem


class TestCoffeeService:
    """Тесты валидации параметров кофе."""

    def test_validate_weight_valid(self):
        """Корректный вес."""
        is_valid, error = CoffeeService.validate_weight(200, 500)
        assert is_valid is True
        assert error is None

    def test_validate_weight_not_multiple_of_50(self):
        """Вес не кратен 50."""
        is_valid, error = CoffeeService.validate_weight(75, 500)
        assert is_valid is False
        assert 'кратен 50' in error

    def test_validate_weight_zero(self):
        """Нулевой вес."""
        is_valid, error = CoffeeService.validate_weight(0, 500)
        assert is_valid is False
        assert 'Укажите вес' in error

    def test_validate_weight_negative(self):
        """Отрицательный вес."""
        is_valid, error = CoffeeService.validate_weight(-50, 500)
        assert is_valid is False

    def test_validate_weight_exceeds_stock(self):
        """Превышение остатка."""
        is_valid, error = CoffeeService.validate_weight(600, 500)
        assert is_valid is False
        assert '600 г' in error

    def test_validate_weight_equal_stock(self):
        """Вес равен остатку."""
        is_valid, error = CoffeeService.validate_weight(500, 500)
        assert is_valid is True

    def test_validate_brewing_method_beans_no_method(self):
        """Зёрна без brewing_method — OK."""
        is_valid, error = CoffeeService.validate_brewing_method('beans', None)
        assert is_valid is True
        assert error is None

    def test_validate_brewing_method_ground_with_method(self):
        """Молотый с brewing_method — OK."""
        is_valid, error = CoffeeService.validate_brewing_method('ground', 'turka')
        assert is_valid is True

    def test_validate_brewing_method_ground_no_method(self):
        """Молотый без brewing_method — ошибка."""
        is_valid, error = CoffeeService.validate_brewing_method('ground', None)
        assert is_valid is False
        assert 'способ заваривания' in error

    def test_validate_all_complete(self, coffee_beans):
        """Полная валидация: все параметры корректны."""
        is_valid, error = CoffeeService.validate_all(
            coffee_beans, 200, 'beans', None
        )
        assert is_valid is True

    def test_validate_all_weight_exceeds_stock(self, coffee_beans):
        """Полная валидация: вес > stock."""
        is_valid, error = CoffeeService.validate_all(
            coffee_beans, 2000, 'beans', None
        )
        assert is_valid is False

    def test_get_available_weights(self, coffee_beans):
        """Доступные веса."""
        weights = CoffeeService.get_available_weights(coffee_beans)
        assert 50 in weights
        assert 200 in weights
        assert 1000 in weights
        assert 1001 not in weights  # stock = 1000

    def test_get_available_weights_empty_stock(self):
        """Нет доступных весов при stock=0."""
        from coffee_shop.apps.catalog.models import Product
        product = Product(stock=0, price_per_50g=Decimal('100'))
        weights = CoffeeService.get_available_weights(product)
        assert weights == []

    def test_all_brewing_methods_exist(self):
        """Все способы заваривания существуют."""
        methods = OrderItem.BREWING_METHOD_CHOICES
        values = [m[0] for m in methods]
        assert 'turka' in values
        assert 'espresso' in values
        assert 'geyser' in values
        assert 'pourover' in values
        assert 'siphon' in values
        assert 'aeropress' in values
        assert 'chemex' in values
        assert 'french_press' in values
        assert 'capping' in values
        assert 'filter_machine' in values
        assert 'order' not in values  # не должно быть ORDER
