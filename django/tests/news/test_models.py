"""Tests for News model."""
from django.utils import timezone
from datetime import timedelta
import pytest

from coffee_shop.apps.news.models import News


pytestmark = pytest.mark.django_db


class TestNewsModel:
    """Тесты модели News."""

    def test_create_news(self):
        """Создание новости."""
        now = timezone.now()
        news = News.objects.create(
            title='Тестовая новость',
            slug='test-news',
            content='Содержание новости',
            is_published=True,
            published_at=now,
        )

        assert news.pk is not None
        assert str(news) == 'Тестовая новость'
        assert news.is_published is True

    def test_news_string_representation(self):
        """Строковое представление."""
        news = News.objects.create(
            title='Hello World',
            slug='hello-world',
            content='Content',
        )
        assert str(news) == 'Hello World'

    def test_news_default_published(self):
        """По умолчанию новость опубликована."""
        news = News.objects.create(
            title='Default published',
            slug='default-pub',
            content='Content',
        )
        assert news.is_published is True

    def test_news_auto_timestamps(self):
        """Автоматические временные метки."""
        news = News.objects.create(
            title='Timestamps test',
            slug='timestamps',
            content='Content',
        )
        assert news.created_at is not None
        assert news.updated_at is not None

    def test_news_save_sets_published_at(self):
        """save() устанавливает published_at если не задан."""
        news = News(
            title='No published_at',
            slug='no-pub-at',
            content='Content',
            is_published=True,
        )
        news.save()
        # published_at должен быть установлен автоматически
        assert news.published_at is not None

    def test_news_unique_slug(self):
        """Slug должен быть уникальным."""
        News.objects.create(
            title='First',
            slug='unique-slug',
            content='Content 1',
        )
        with pytest.raises(Exception):  # IntegrityError
            News.objects.create(
                title='Second',
                slug='unique-slug',
                content='Content 2',
            )

    def test_news_ordering(self):
        """Сортировка по published_at по убыванию."""
        now = timezone.now()
        News.objects.create(
            title='Old news',
            slug='old-news',
            content='Old',
            published_at=now - timedelta(days=2),
        )
        News.objects.create(
            title='New news',
            slug='new-news',
            content='New',
            published_at=now,
        )

        news_list = list(News.objects.all())
        assert news_list[0].title == 'New news'
        assert news_list[1].title == 'Old news'

    def test_published_at_null(self):
        """published_at может быть null."""
        news = News.objects.create(
            title='No date',
            slug='no-date',
            content='Content',
            published_at=None,
        )
        assert news.published_at is None


@pytest.fixture
def published_news():
    now = timezone.now()
    return News.objects.create(
        title='Published',
        slug='published',
        content='Published content',
        is_published=True,
        published_at=now,
    )


@pytest.fixture
def unpublished_news():
    now = timezone.now()
    return News.objects.create(
        title='Unpublished',
        slug='unpublished',
        content='Unpublished content',
        is_published=False,
        published_at=now,
    )


@pytest.fixture
def future_news():
    now = timezone.now()
    return News.objects.create(
        title='Future',
        slug='future',
        content='Future content',
        is_published=True,
        published_at=now + timedelta(days=1),
    )


class TestNewsQueryManager:
    """Тесты queryset для News."""

    def test_filter_published(self, published_news, unpublished_news, future_news):
        """Фильтрация опубликованных новостей."""
        published = News.objects.filter(
            is_published=True,
            published_at__lte=timezone.now(),
        )
        slugs = list(published.values_list('slug', flat=True))

        assert 'published' in slugs
        assert 'unpublished' not in slugs
        assert 'future' not in slugs
