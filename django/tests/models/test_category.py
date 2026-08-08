"""Tests for Category model."""
import pytest
from django.core.exceptions import ValidationError
from coffee_shop.apps.catalog.models import Category


pytestmark = pytest.mark.django_db


class TestCategory:
    """Тесты модели Category."""

    def test_create_category(self):
        category = Category.objects.create(
            name='Эспрессо смеси',
            slug='espresso-blends',
            order=1,
        )
        assert category.name == 'Эспрессо смеси'
        assert category.slug == 'espresso-blends'
        assert category.order == 1
        assert category.is_active is True
        assert category.parent is None
        assert category.children.count() == 0

    def test_create_nested_category(self):
        parent = Category.objects.create(name='Кофе', slug='coffee')
        child = Category.objects.create(
            name='Эспрессо',
            slug='espresso',
            parent=parent,
        )
        assert child.parent == parent
        assert parent.children.count() == 1
        assert parent.children.first() == child

    def test_category_str(self):
        category = Category.objects.create(name='Test Category', slug='test')
        assert str(category) == 'Test Category'

    def test_unique_slug(self):
        Category.objects.create(name='First', slug='unique-slug')
        with pytest.raises(Exception):  # IntegrityError
            Category.objects.create(name='Second', slug='unique-slug')

    def test_delete_parent_cascades_children(self):
        parent = Category.objects.create(name='Parent', slug='parent')
        child = Category.objects.create(name='Child', slug='child', parent=parent)
        parent.delete()
        assert not Category.objects.filter(pk=child.pk).exists()

    def test_is_active_default(self):
        category = Category.objects.create(name='Test', slug='test')
        assert category.is_active is True

    def test_default_order(self):
        category = Category.objects.create(name='Test', slug='test')
        assert category.order == 0

    def test_ordering(self):
        Category.objects.create(name='Z', slug='z', order=2)
        Category.objects.create(name='A', slug='a', order=1)
        Category.objects.create(name='M', slug='m', order=0)
        assert list(Category.objects.values_list('slug', flat=True)) == ['m', 'a', 'z']
