"""Serializers for news app."""
from rest_framework import serializers

from .models import News, Promotion


class NewsListSerializer(serializers.ModelSerializer):
    """Список новостей (минимальные поля)."""

    class Meta:
        model = News
        fields = ['id', 'title', 'slug', 'image', 'published_at']


class NewsDetailSerializer(serializers.ModelSerializer):
    """Детальная информация о новости."""

    class Meta:
        model = News
        fields = [
            'id', 'title', 'slug', 'content', 'image',
            'is_published', 'published_at', 'created_at', 'updated_at',
        ]


class PromotionListSerializer(serializers.ModelSerializer):
    """Список акций (минимальные поля)."""

    is_current = serializers.BooleanField(read_only=True)

    class Meta:
        model = Promotion
        fields = [
            'id', 'title', 'slug', 'image',
            'start_date', 'end_date', 'is_current',
        ]


class PromotionDetailSerializer(serializers.ModelSerializer):
    """Детальная информация об акции."""

    is_current = serializers.BooleanField(read_only=True)

    class Meta:
        model = Promotion
        fields = [
            'id', 'title', 'slug', 'description', 'image',
            'start_date', 'end_date', 'is_active',
            'is_current', 'created_at', 'updated_at',
        ]
