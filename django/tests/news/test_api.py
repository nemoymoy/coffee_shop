"""Tests for news serializers."""
import pytest
from decimal import Decimal
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from coffee_shop.apps.news.models import News, Promotion


pytestmark = pytest.mark.django_db


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def news_item():
    now = timezone.now()
    return News.objects.create(
        title='Serializer Test News',
        slug='serializer-test',
        content='Test content for serializer',
        is_published=True,
        published_at=now,
    )


@pytest.fixture
def promo_item():
    now = timezone.now()
    return Promotion.objects.create(
        title='Serializer Test Promo',
        slug='serializer-promo',
        description='Test promo description',
        start_date=now,
        end_date=now + timedelta(days=30),
        is_active=True,
    )


class TestNewsAPI:
    """Тесты News API."""

    def test_api_news_list(self, api_client, news_item):
        response = api_client.get('/api/news/news/')
        assert response.status_code == 200
        assert len(response.data) >= 1

    def test_api_news_detail(self, api_client, news_item):
        response = api_client.get(f'/api/news/news/{news_item.id}/')
        assert response.status_code == 200
        assert response.data['title'] == 'Serializer Test News'
        assert response.data['slug'] == 'serializer-test'
        assert response.data['content'] == 'Test content for serializer'

    def test_api_news_list_fields(self, api_client, news_item):
        """List возвращает минимальные поля."""
        response = api_client.get('/api/news/news/')
        assert 'id' in response.data[0]
        assert 'title' in response.data[0]
        assert 'slug' in response.data[0]
        assert 'content' not in response.data[0]  # List без контента

    def test_api_news_detail_fields(self, api_client, news_item):
        """Detail возвращает все поля."""
        response = api_client.get(f'/api/news/news/{news_item.id}/')
        assert 'content' in response.data
        assert 'created_at' in response.data
        assert 'updated_at' in response.data
        assert 'is_published' in response.data

    def test_api_news_search(self, api_client, news_item):
        response = api_client.get('/api/news/news/?search=Serializer')
        assert response.status_code == 200
        assert len(response.data) >= 1

    def test_api_news_ordering(self, api_client):
        now = timezone.now()
        News.objects.create(
            title='Old News',
            slug='old-news',
            content='Old',
            is_published=True,
            published_at=now - timedelta(days=1),
        )
        News.objects.create(
            title='New News',
            slug='new-news',
            content='New',
            is_published=True,
            published_at=now,
        )
        response = api_client.get('/api/news/news/?ordering=-published_at')
        assert response.status_code == 200
        assert response.data[0]['title'] == 'New News'


class TestPromotionAPI:
    """Тесты Promotion API."""

    def test_api_promotions_list(self, api_client, promo_item):
        response = api_client.get('/api/news/promotions/')
        assert response.status_code == 200
        assert len(response.data) >= 1

    def test_api_promotions_detail(self, api_client, promo_item):
        response = api_client.get(f'/api/news/promotions/{promo_item.id}/')
        assert response.status_code == 200
        assert response.data['title'] == 'Serializer Test Promo'
        assert response.data['description'] == 'Test promo description'

    def test_api_promotions_current_field(self, api_client, promo_item):
        response = api_client.get(f'/api/news/promotions/{promo_item.id}/')
        assert 'is_current' in response.data

    def test_api_promotions_search(self, api_client, promo_item):
        response = api_client.get('/api/news/promotions/?search=Serializer')
        assert response.status_code == 200
        assert len(response.data) >= 1
