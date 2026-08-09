"""API views for news app."""
from django.utils import timezone
from rest_framework import viewsets
from rest_framework.permissions import AllowAny
from rest_framework.filters import SearchFilter, OrderingFilter
from django_filters.rest_framework import DjangoFilterBackend

from ..models import News, Promotion
from ..serializers import (
    NewsListSerializer,
    NewsDetailSerializer,
    PromotionListSerializer,
    PromotionDetailSerializer,
)


class NewsViewSet(viewsets.ReadOnlyModelViewSet):
    """API для новостей."""

    queryset = News.objects.filter(
        is_published=True,
        published_at__lte=timezone.now()
    ).order_by('-published_at')
    filter_backends = [SearchFilter, OrderingFilter, DjangoFilterBackend]
    search_fields = ['title', 'content']
    ordering_fields = ['published_at', 'created_at']
    ordering = ['-published_at']
    filterset_fields = ['is_published']

    def get_serializer_class(self):
        if self.action == 'list':
            return NewsListSerializer
        return NewsDetailSerializer


class PromotionViewSet(viewsets.ReadOnlyModelViewSet):
    """API для акций."""

    queryset = Promotion.objects.filter(
        is_active=True,
        end_date__gte=timezone.now()
    ).order_by('-start_date')
    filter_backends = [SearchFilter, OrderingFilter, DjangoFilterBackend]
    search_fields = ['title', 'description']
    ordering_fields = ['start_date', 'end_date']
    ordering = ['-start_date']
    filterset_fields = ['is_active']

    def get_serializer_class(self):
        if self.action == 'list':
            return PromotionListSerializer
        return PromotionDetailSerializer
