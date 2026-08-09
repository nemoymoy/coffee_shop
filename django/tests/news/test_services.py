"""Tests for NewsService and PromotionService."""
from django.utils import timezone
from datetime import timedelta
import pytest

from coffee_shop.apps.news.models import News, Promotion
from coffee_shop.apps.news.services import NewsService, PromotionService


pytestmark = pytest.mark.django_db


@pytest.fixture
def news_data():
    now = timezone.now()
    return {
        'published': News.objects.create(
            title='Published News',
            slug='published-news',
            content='Published content',
            is_published=True,
            published_at=now,
        ),
        'unpublished': News.objects.create(
            title='Unpublished News',
            slug='unpublished-news',
            content='Unpublished content',
            is_published=False,
            published_at=now,
        ),
        'future': News.objects.create(
            title='Future News',
            slug='future-news',
            content='Future content',
            is_published=True,
            published_at=now + timedelta(days=1),
        ),
    }


@pytest.fixture
def promo_data():
    now = timezone.now()
    return {
        'active': Promotion.objects.create(
            title='Active Promo',
            slug='active-promo',
            description='Active promotion',
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=30),
            is_active=True,
        ),
        'expired': Promotion.objects.create(
            title='Expired Promo',
            slug='expired-promo',
            description='Expired promotion',
            start_date=now - timedelta(days=30),
            end_date=now - timedelta(days=1),
            is_active=True,
        ),
        'inactive': Promotion.objects.create(
            title='Inactive Promo',
            slug='inactive-promo',
            description='Inactive promotion',
            start_date=now - timedelta(days=1),
            end_date=now + timedelta(days=30),
            is_active=False,
        ),
    }


class TestNewsService:
    """Тесты NewsService."""

    def test_get_published_news(self, news_data):
        """Получение опубликованных новостей."""
        result = NewsService.get_published_news()
        slugs = list(result.values_list('slug', flat=True))

        assert 'published-news' in slugs
        assert 'unpublished-news' not in slugs
        assert 'future-news' not in slugs

    def test_get_published_news_limit(self, news_data):
        """Ограничение количества новостей."""
        News.objects.create(
            title='Another',
            slug='another',
            content='Content',
            is_published=True,
            published_at=timezone.now() - timedelta(hours=1),
        )
        result = NewsService.get_published_news(limit=1)
        assert result.count() == 1

    def test_get_news_by_slug_found(self, news_data):
        """Поиск новости по slug."""
        news = NewsService.get_news_by_slug('published-news')
        assert news is not None
        assert news.title == 'Published News'

    def test_get_news_by_slug_not_found(self):
        """Поиск несуществующей новости."""
        result = NewsService.get_news_by_slug('nonexistent')
        assert result is None

    def test_search_news(self, news_data):
        """Поиск новостей по заголовку."""
        News.objects.create(
            title='Кофе со скидкой',
            slug='sale-coffee',
            content='Great coffee deal',
            is_published=True,
            published_at=timezone.now(),
        )
        results = NewsService.search_news('скидкой')
        assert results.count() == 1
        assert results.first().slug == 'sale-coffee'


class TestPromotionService:
    """Тесты PromotionService."""

    def test_get_active_promotions(self, promo_data):
        """Получение активных акций."""
        result = PromotionService.get_active_promotions()
        slugs = list(result.values_list('slug', flat=True))

        assert 'active-promo' in slugs
        assert 'expired-promo' not in slugs
        assert 'inactive-promo' not in slugs

    def test_get_active_promotions_limit(self, promo_data):
        """Ограничение количества акций."""
        Promotion.objects.create(
            title='Another Promo',
            slug='another-promo',
            description='Another promotion',
            start_date=timezone.now(),
            end_date=timezone.now() + timedelta(days=10),
            is_active=True,
        )
        result = PromotionService.get_active_promotions(limit=1)
        assert result.count() == 1

    def test_get_promotion_by_slug_found(self, promo_data):
        """Поиск акции по slug."""
        promo = PromotionService.get_promotion_by_slug('active-promo')
        assert promo is not None
        assert promo.title == 'Active Promo'

    def test_get_promotion_by_slug_not_found(self):
        """Поиск несуществующей акции."""
        result = PromotionService.get_promotion_by_slug('nonexistent')
        assert result is None

    def test_get_current_promotions(self, promo_data):
        """Текущие акции."""
        result = PromotionService.get_current_promotions()
        slugs = list(result.values_list('slug', flat=True))
        assert 'active-promo' in slugs
