"""Tests for CoffeeForm."""
import pytest
from django.core.exceptions import ValidationError

from coffee_shop.apps.catalog.forms.coffee_form import CoffeeForm
from coffee_shop.apps.catalog.models import Product, Category


pytestmark = pytest.mark.django_db


@pytest.fixture
def category():
    return Category.objects.create(name='Кофе', slug='coffee', is_active=True)


@pytest.fixture
def coffee_product(category):
    return Product.objects.create(
        name='Эфиопия Иргачефф',
        slug='ethiopia-irgacheff',
        category=category,
        product_type='coffee',
        price_per_50g=150.00,
        stock=500,
        allow_grinding=True,
        available_brewing_methods=['turka', 'espresso', 'french_press'],
        coffee_type='Арабика',
        roast_level='medium',
    )


class TestCoffeeForm:
    """Тесты формы выбора параметров кофе."""

    def test_form_initialization(self, coffee_product):
        """Форма инициализируется с правильными weight choices."""
        form = CoffeeForm(product=coffee_product)
        weights = [c[0] for c in form.fields['weight'].choices]
        assert 50 in weights
        assert 100 in weights
        assert 500 in weights
        # 550 > 500 stock, so not included
        assert 550 not in weights

    def test_form_with_zero_stock(self, category):
        """Форма с stock=0 отключает weight."""
        product = Product.objects.create(
            name='Нет в наличии',
            slug='no-stock',
            category=category,
            product_type='coffee',
            price_per_50g=100,
            stock=0,
        )
        form = CoffeeForm(product=product)
        assert form.fields['weight'].widget.attrs.get('disabled') == 'disabled'

    def test_form_valid_beans(self, coffee_product):
        """Валидная форма: зёрна."""
        form = CoffeeForm(
            product=coffee_product,
            data={
                'weight': 100,
                'coffee_form': 'beans',
            }
        )
        assert form.is_valid() is True

    def test_form_valid_ground_with_method(self, coffee_product):
        """Валидная форма: молотый с методом."""
        form = CoffeeForm(
            product=coffee_product,
            data={
                'weight': 100,
                'coffee_form': 'ground',
                'brewing_method': 'turka',
            }
        )
        assert form.is_valid() is True

    def test_form_invalid_weight_not_multiple_50(self, coffee_product):
        """Вес не кратен 50."""
        form = CoffeeForm(
            product=coffee_product,
            data={
                'weight': 75,
                'coffee_form': 'beans',
            }
        )
        assert form.is_valid() is False
        assert 'weight' in form.errors

    def test_form_invalid_ground_no_method(self, coffee_product):
        """Молотый без brewing_method."""
        form = CoffeeForm(
            product=coffee_product,
            data={
                'weight': 100,
                'coffee_form': 'ground',
            }
        )
        assert form.is_valid() is False

    def test_form_exceeds_stock(self, coffee_product):
        """Превышение stock."""
        form = CoffeeForm(
            product=coffee_product,
            data={
                'weight': 600,
                'coffee_form': 'beans',
            }
        )
        assert form.is_valid() is False

    def test_form_invalid_brewing_method(self, coffee_product):
        """Некорректная комбинация: молотый, метод не из списка."""
        form = CoffeeForm(
            product=coffee_product,
            data={
                'weight': 100,
                'coffee_form': 'ground',
                'brewing_method': 'invalid_method',
            }
        )
        assert form.is_valid() is False
