"""Serializers for catalog app."""
from rest_framework import serializers

from coffee_shop.apps.catalog.models import Category, Product, Review


class CategorySerializer(serializers.ModelSerializer):
    """Сериализатор категории."""
    children = serializers.SerializerMethodField()
    product_count = serializers.SerializerMethodField()

    class Meta:
        model = Category
        fields = [
            'id', 'name', 'slug', 'parent', 'order',
            'is_active', 'created_at', 'updated_at',
            'children', 'product_count',
        ]
        read_only_fields = ['created_at', 'updated_at']

    def get_children(self, obj):
        children = obj.children.filter(is_active=True)
        return CategorySerializer(children, many=True, context=self.context).data

    def get_product_count(self, obj):
        return obj.products.filter(is_available=True).count()


class ProductSerializer(serializers.ModelSerializer):
    """Сериализатор товара."""
    category_name = serializers.CharField(source='category.name', read_only=True)
    average_rating = serializers.SerializerMethodField()
    review_count = serializers.SerializerMethodField()

    class Meta:
        model = Product
        fields = [
            'id', 'name', 'slug', 'description', 'category',
            'category_name', 'product_type', 'price_per_50g',
            'base_price', 'stock', 'image', 'is_available',
            'allow_grinding', 'available_brewing_methods',
            'allergens', 'coffee_type', 'roast_level',
            'origin_region', 'processing_method', 'sca_score',
            'tasting_notes', 'created_at', 'updated_at',
            'average_rating', 'review_count',
        ]
        read_only_fields = ['created_at', 'updated_at', 'slug']

    def get_average_rating(self, obj):
        approved_reviews = obj.reviews.filter(is_approved=True)
        if approved_reviews.exists():
            return round(approved_reviews.aggregate(serializers.Avg('rating'))['rating__avg'], 1)
        return None

    def get_review_count(self, obj):
        return obj.reviews.filter(is_approved=True).count()


class ReviewSerializer(serializers.ModelSerializer):
    """Сериализатор отзыва."""
    user_name = serializers.CharField(
        source='user.get_full_name',
        read_only=True,
        default=None
    )
    username = serializers.CharField(
        source='user.username',
        read_only=True
    )

    class Meta:
        model = Review
        fields = [
            'id', 'product', 'user', 'user_name', 'username',
            'rating', 'comment', 'is_approved', 'created_at',
            'updated_at',
        ]
        read_only_fields = ['user', 'created_at', 'updated_at']

    def create(self, validated_data):
        """Создание отзыва с автоматическим назначением пользователя."""
        request = self.context.get('request')
        if request and hasattr(request, 'user'):
            validated_data['user'] = request.user
        return super().create(validated_data)
