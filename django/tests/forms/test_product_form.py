"""Tests for ProductForm (filter form)."""
import pytest

from coffee_shop.apps.catalog.forms.product_form import ProductForm
from coffee_shop.apps.catalog.models import Product, Category


class TestProductForm:
    """Тесты формы фильтрации товаров."""

    def test_form_initialization(self):
        """Форма инициализируется без ошибок."""
        form = ProductForm()
        assert form.fields['roast_level'].choices == Product.ROAST_CHOICES
        assert len(form.fields['roast_level'].choices) > 0

    def test_form_has_all_fields(self):
        """Форма содержит все нужные поля."""
        form = ProductForm()
        expected_fields = [
            'category', 'min_price', 'max_price',
            'roast_level', 'processing_method', 'min_sca',
        ]
        for field in expected_fields:
            assert field in form.fields

    def test_form_processin_method_choices(self):
        """Проверка выбора processing_method."""
        form = ProductForm()
        choices = [c[0] for c in form.fields['processing_method'].choices]
        assert 'natural' in choices
        assert 'washed' in choices
        assert 'honey' in choices
        assert 'anaerobic' in choices
        assert 'other' in choices

    def test_form_with_categories(self):
        """Форма с передачей categories."""
        form = ProductForm(categories=[])
        assert form is not None

    def test_form_roast_choices_from_product_model(self):
        """ROAST_CHOICES берётся из модели Product."""
        form = ProductForm()
        assert form.fields['roast_level'].choices == Product.ROAST_CHOICES
        # Убедимся, что все уровни на месте
        values = [v[0] for v in form.fields['roast_level'].choices]
        assert 'light' in values
        assert 'medium' in values
        assert 'dark' in values
        assert 'medium-dark' in values
        assert 'dark-roast' in values
