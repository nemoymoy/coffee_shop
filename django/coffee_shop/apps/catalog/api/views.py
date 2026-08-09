"""API views for catalog app."""
from rest_framework import viewsets, filters, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend

from coffee_shop.apps.catalog.models import Category, Product, Review
from coffee_shop.apps.catalog.serializers import (
    CategorySerializer,
    ProductSerializer,
    ReviewSerializer,
)


class CategoryViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only API for categories."""

    queryset = Category.objects.filter(is_active=True)
    serializer_class = CategorySerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ['parent', 'is_active']
    search_fields = ['name']
    ordering_fields = ['order', 'name']
    ordering = ['order']

    @action(detail=True, methods=['get'])
    def products(self, request, pk=None):
        """Получить товары категории."""
        category = self.get_object()
        products = category.products.filter(is_available=True)
        serializer = ProductSerializer(
            products, many=True, context={'request': request}
        )
        return Response(serializer.data)


class ProductViewSet(viewsets.ReadOnlyModelViewSet):
    """Read-only API for products."""

    queryset = Product.objects.select_related('category').filter(is_available=True)
    serializer_class = ProductSerializer
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = [
        'product_type', 'category', 'is_available',
        'roast_level', 'processing_method',
    ]
    search_fields = ['name', 'description', 'origin_region']
    ordering_fields = ['name', 'price_per_50g', 'base_price', 'stock', 'sca_score', 'created_at']
    ordering = ['-created_at']

    @action(detail=True, methods=['get'])
    def reviews(self, request, pk=None):
        """Получить отзывы для товара."""
        product = self.get_object()
        reviews = product.reviews.filter(is_approved=True)
        serializer = ReviewSerializer(
            reviews, many=True, context={'request': request}
        )
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def featured(self, request):
        """Получить рекомендуемые товары (с высоким SCA)."""
        products = self.queryset.filter(
            product_type='coffee',
            sca_score__gte=85
        ).order_by('-sca_score')[:6]
        serializer = self.get_serializer(products, many=True)
        return Response(serializer.data)


class ReviewViewSet(viewsets.ModelViewSet):
    """API для управления отзывами."""

    serializer_class = ReviewSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ['product', 'is_approved']

    def get_queryset(self):
        return Review.objects.select_related('product', 'user').all()

    def perform_create(self, serializer):
        """Создание отзыва с привязкой к текущему пользователю."""
        serializer.save(user=self.request.user)

    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        """Одобрить отзыв (для администраторов)."""
        review = self.get_object()
        review.is_approved = True
        review.save()
        serializer = self.get_serializer(review)
        return Response(serializer.data)
