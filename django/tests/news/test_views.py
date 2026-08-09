"""Tests for news views."""
import pytest
from django.utils import timezone
from datetime import timedelta
from django.urls import reverse

from coffee_shop.apps.news.models import News, Promotion


pytestmark = pytest.mark.django_db


@pytest.fixture
def published_news():
    now = timezone.now()
    return News.objects.create(
        title='Test News',
        slug='test-news',
        content='Test content',
        is_published=True,
        published_at=now,
    )


@pytest.fixture
def future_news():
    now = timezone.now()
    return News.objects.create(
        title='Future News',
        slug='future-news',
        content='Future content',
        is_published=True,
        published_at=now + timedelta(days=1),
    )


@pytest.fixture
def active_promo():
    now = timezone.now()
    return Promotion.objects.create(
        title='Test Promo',
        slug='test-promo',
        description='Test promo description',
        start_date=now - timedelta(days=1),
        end_date=now + timedelta(days=30),
        is_active=True,
    )


class TestNewsListView:
    """Тесты news_list."""

    def test_news_list_page_loads(self, client, published_news):
        response = client.get(reverse('news:news_list'))
        assert response.status_code == 200

    def test_news_list_shows_published(self, client, published_news):
        response = client.get(reverse('news:news_list'))
        assert b'Test News' in response.content

    def test_news_list_hides_unpublished(self, client):
        News.objects.create(
            title='Hidden',
            slug='hidden',
            content='Hidden content',
            is_published=False,
            published_at=timezone.now(),
        )
        response = client.get(reverse('news:news_list'))
        assert b'Hidden' not in response.content

    def test_news_list_hides_future(self, client, future_news):
        response = client.get(reverse('news:news_list'))
        assert b'Future News' not in response.content


class TestNewsDetailView:
    """Тесты news_detail."""

    def test_news_detail_page_loads(self, client, published_news):
        response = client.get(
            reverse('news:news_detail', args=['test-news'])
        )
        assert response.status_code == 200

    def test_news_detail_shows_content(self, client, published_news):
        response = client.get(
            reverse('news:news_detail', args=['test-news'])
        )
        assert b'Test content' in response.content

    def test_news_detail_not_found(self, client):
        response = client.get(
            reverse('news:news_detail', args=['nonexistent'])
        )
        assert response.status_code == 404


class TestPromotionsListView:
    """Тесты promotions_list."""

    def test_promotions_list_page_loads(self, client, active_promo):
        response = client.get(reverse('news:promotions_list'))
        assert response.status_code == 200

    def test_promotions_list_shows_active(self, client, active_promo):
        response = client.get(reverse('news:promotions_list'))
        assert b'Test Promo' in response.content

    def test_promotions_list_hides_expired(self, client):
        now = timezone.now()
        Promotion.objects.create(
            title='Expired',
            slug='expired-promo',
            description='Expired',
            start_date=now - timedelta(days=30),
            end_date=now - timedelta(days=1),
            is_active=True,
        )
        response = client.get(reverse('news:promotions_list'))
        assert b'Expired' not in response.content

    def test_promotions_list_hides_inactive(self, client):
        now = timezone.now()
        Promotion.objects.create(
            title='Inactive',
            slug='inactive-promo',
            description='Inactive',
            start_date=now,
            end_date=now + timedelta(days=30),
            is_active=False,
        )
        response = client.get(reverse('news:promotions_list'))
        assert b'Inactive' not in response.content
