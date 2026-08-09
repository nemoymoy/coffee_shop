"""Views for news app."""
from django.shortcuts import render, get_object_or_404
from django.utils import timezone

from .models import News
from .services import NewsService, PromotionService


def news_list(request):
    """Список новостей."""
    news = NewsService.get_published_news()

    context = {
        'news': news,
    }
    return render(request, 'news.html', context)


def news_detail(request, slug):
    """Детальная страница новости."""
    news = get_object_or_404(News, slug=slug, is_published=True)

    context = {
        'news': news,
    }
    return render(request, 'news_detail.html', context)


def promotions_list(request):
    """Список акций."""
    promotions = PromotionService.get_active_promotions()

    context = {
        'promotions': promotions,
    }
    return render(request, 'promotions.html', context)
