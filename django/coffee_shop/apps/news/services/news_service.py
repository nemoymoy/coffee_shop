"""News service - business logic for news app."""
from django.db.models import Q
from django.utils import timezone

from ..models import News, Promotion


class NewsService:
    """Сервис для работы с новостями."""

    @staticmethod
    def get_published_news(limit=None):
        """Получить список опубликованных новостей.

        Args:
            limit: Ограничение количества результатов.

        Returns:
            QuerySet[News]
        """
        queryset = News.objects.filter(
            is_published=True,
            published_at__lte=timezone.now()
        ).order_by('-published_at')

        if limit is not None:
            queryset = queryset[:limit]

        return queryset

    @staticmethod
    def get_news_by_slug(slug):
        """Получить новость по slug.

        Args:
            slug: URL-адрес новости

        Returns:
            News или None
        """
        try:
            return News.objects.get(
                slug=slug,
                is_published=True,
                published_at__lte=timezone.now()
            )
        except News.DoesNotExist:
            return None

    @staticmethod
    def search_news(query):
        """Поиск новостей по заголовку или содержанию.

        Args:
            query: поисковый запрос

        Returns:
            QuerySet[News]
        """
        return News.objects.filter(
            is_published=True,
            published_at__lte=timezone.now(),
        ).filter(
            Q(title__icontains=query) | Q(content__icontains=query)
        )


class PromotionService:
    """Сервис для работы с акциями."""

    @staticmethod
    def get_active_promotions(limit=None):
        """Получить список активных акций.

        Args:
            limit: Ограничение количества результатов.

        Returns:
            QuerySet[Promotion]
        """
        now = timezone.now()
        queryset = Promotion.objects.filter(
            is_active=True,
            start_date__lte=now,
            end_date__gte=now
        ).order_by('-start_date')

        if limit is not None:
            queryset = queryset[:limit]

        return queryset

    @staticmethod
    def get_promotion_by_slug(slug):
        """Получить активную акцию по slug.

        Args:
            slug: URL-адрес акции

        Returns:
            Promotion или None
        """
        now = timezone.now()
        try:
            return Promotion.objects.get(
                slug=slug,
                is_active=True,
                start_date__lte=now,
                end_date__gte=now,
            )
        except Promotion.DoesNotExist:
            return None
