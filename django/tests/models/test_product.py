"""Tests for Product model."""
from django.core.exceptions import ValidationError
import pytest

from coffee_shop.apps.catalog.models import Product, Category


pytestmark = pytest.mark.django_db


@pytest.fixture
def category():
    return Category.objects.create(name='Кофе', slug='coffee', is_active=True)


class TestProductModel:
    """Тесты модели Product."""

    def test_create_coffee_product(self, category):
        """Создание кофейного продукта."""
        product = Product.objects.create(
            name='Эфиопия Иргачефф',
            slug='ethiopia-irgacheff',
            category=category,
            product_type='coffee',
            price_per_50g=150.00,
            stock=1000,
            allow_grinding=True,
            available_brewing_methods=['turka', 'espresso', 'french_press'],
            coffee_type='Арабика',
            roast_level='medium',
            origin_region='Эфиопия',
            processing_method='washed',
            sca_score=86,
            tasting_notes='Цветочный, ягодный'
        )

        assert product.pk is not None
        assert product.name == 'Эфиопия Иргачефф'
        assert product.product_type == 'coffee'
        assert str(product) == 'Эфиопия Иргачефф'

    def test_create_non_coffee_product(self, category):
        """Создание не кофейного продукта."""
        product = Product.objects.create(
            name='Чизкейк',
            slug='cheesecake',
            category=category,
            product_type='other',
            base_price=350.00,
            price_per_50g=100.00,
            stock=20
        )

        assert product.product_type == 'other'
        assert product.stock > 0

    def test_stock_property(self, category):
        """Свойства stock."""
        product = Product.objects.create(
            name='Тест',
            slug='test',
            category=category,
            price_per_50g=100.00,
            stock=0
        )
        assert product.is_in_stock is False

        product.stock = 100
        product.save()
        assert product.is_in_stock is True

    def test_max_weight_grams(self, category):
        """Максимальный вес равен stock."""
        product = Product.objects.create(
            name='Тест',
            slug='test2',
            category=category,
            price_per_50g=100.00,
            stock=500
        )
        assert product.max_weight_grams == 500

    def test_clean_grinding_requires_brewing_methods(self, category):
        """Валидация: allow_grinding требует brewing_methods."""
        product = Product(
            name='Тест',
            slug='test-grind',
            category=category,
            allow_grinding=True,
            available_brewing_methods=[]
        )
        with pytest.raises(ValidationError):
            product.clean()

    def test_clean_grinding_with_methods(self, category):
        """Валидация: allow_grinding с brewing_methods проходит."""
        product = Product(
            name='Тест',
            slug='test-grind-ok',
            category=category,
            allow_grinding=True,
            available_brewing_methods=['turka', 'espresso']
        )
        # Не должно выбросить исключение
        product.clean()

    def test_sca_score_validator(self, category):
        """Валидация SCA score (0-100)."""
        # Корректное значение
        product = Product(
            name='Тест',
            slug='test-sca',
            category=category,
            price_per_50g=100.00,
            sca_score=85
        )
        product.full_clean()  # Не должно выбросить

        # Неверное значение
        product.sca_score = 101
        with pytest.raises(ValidationError):
            product.full_clean()

        product.sca_score = -1
        with pytest.raises(ValidationError):
            product.full_clean()


class TestCategoryModel:
    """Тесты модели Category."""

    def test_create_category(self):
        category = Category.objects.create(
            name='Кофе',
            slug='coffee',
            is_active=True
        )
        assert str(category) == 'Кофе'
        assert category.slug == 'coffee'

    def test_category_with_parent(self):
        """Вложенная категория."""
        parent = Category.objects.create(
            name='Кофе',
            slug='coffee',
            is_active=True
        )
        child = Category.objects.create(
            name='Зерновой кофе',
            slug='coffee-beans',
            parent=parent,
            is_active=True
        )

        assert child.parent == parent
        assert parent.children.count() == 1

    def test_category_order(self):
        """Сортировка по order."""
        Category.objects.create(name='ZZZ', slug='zzz', order=10)
        Category.objects.create(name='AAA', slug='aaa', order=1)
        Category.objects.create(name='MMM', slug='mmm', order=5)

        categories = Category.objects.all()
        assert categories[0].name == 'AAA'
