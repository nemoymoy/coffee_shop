"""Views for news app."""
from django.shortcuts import render, get_object_or_404
from django.utils import timezone
from .models import News, Promotion


def news_list(request):
    """Список новостей."""
    news = News.objects.filter(
        is_published=True,
        published_at__lte=timezone.now()
    ).order_by('-published_at')
    
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
    promotions = Promotion.objects.filter(
        is_active=True,
        end_date__gte=timezone.now()
    ).order_by('-start_date')
    
    context = {
        'promotions': promotions,
    }
    return render(request, 'promotions.html', context)
