"""Tests for news forms."""
import pytest
from django import forms
from django.utils import timezone
from datetime import timedelta

from coffee_shop.apps.news.forms import NewsForm, PromotionForm


pytestmark = pytest.mark.django_db


class TestNewsForm:
    """Тесты NewsForm."""

    def test_news_form_valid_data(self):
        form = NewsForm(data={
            'title': 'Valid News',
            'slug': 'valid-news',
            'content': 'Valid content here',
            'is_published': True,
            'published_at': timezone.now().strftime('%Y-%m-%d %H:%M'),
        })
        assert form.is_valid() is True

    def test_news_form_empty_title(self):
        form = NewsForm(data={
            'slug': 'empty-title',
            'content': 'Content',
        })
        assert form.is_valid() is False
        assert 'title' in form.errors

    def test_news_form_empty_slug(self):
        form = NewsForm(data={
            'title': 'Empty Slug',
            'content': 'Content',
        })
        assert form.is_valid() is False
        assert 'slug' in form.errors

    def test_news_form_empty_content(self):
        form = NewsForm(data={
            'title': 'No Content',
            'slug': 'no-content',
        })
        assert form.is_valid() is False
        assert 'content' in form.errors

    def test_news_form_wrong_slug_format(self):
        form = NewsForm(data={
            'title': 'Bad Slug',
            'slug': 'недопустимый slug с пробелами',
            'content': 'Content',
        })
        assert form.is_valid() is False
        assert 'slug' in form.errors

    def test_news_form_widgets(self):
        form = NewsForm()
        widgets = {
            'title': forms.TextInput,
            'content': forms.Textarea,
            'is_published': forms.CheckboxInput,
        }
        for field, expected_widget in widgets.items():
            assert isinstance(form.fields[field].widget, expected_widget)


@pytest.fixture
def promotion_data():
    now = timezone.now()
    return {
        'title': 'Promo Title',
        'slug': 'promo-title',
        'description': 'Promo description',
        'start_date': (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M'),
        'end_date': (now + timedelta(days=30)).strftime('%Y-%m-%d %H:%M'),
        'is_active': True,
    }


class TestPromotionForm:
    """Тесты PromotionForm."""

    def test_promotion_form_valid_data(self, promotion_data):
        form = PromotionForm(data=promotion_data)
        assert form.is_valid() is True

    def test_promotion_form_empty_title(self, promotion_data):
        data = promotion_data.copy()
        data['title'] = ''
        form = PromotionForm(data=data)
        assert form.is_valid() is False
        assert 'title' in form.errors

    def test_promotion_form_empty_description(self, promotion_data):
        data = promotion_data.copy()
        data['description'] = ''
        form = PromotionForm(data=data)
        assert form.is_valid() is False
        assert 'description' in form.errors

    def test_promotion_form_invalid_dates(self):
        """end_date раньше start_date."""
        now = timezone.now()
        form = PromotionForm(data={
            'title': 'Bad Dates',
            'slug': 'bad-dates',
            'description': 'Description',
            'start_date': (now + timedelta(days=10)).strftime('%Y-%m-%d %H:%M'),
            'end_date': (now - timedelta(days=1)).strftime('%Y-%m-%d %H:%M'),
            'is_active': True,
        })
        assert form.is_valid() is False
