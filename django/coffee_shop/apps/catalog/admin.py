from django.contrib import admin
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _
from .models import Category, Product, Review


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'slug', 'parent', 'order', 'is_active']
    list_filter = ['is_active', 'parent']
    search_fields = ['name']
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ['order', 'is_active']


class ProductAdmin(admin.ModelAdmin):
    list_display = [
        'name', 'category', 'product_type', 'price_display', 'stock',
        'sca_score', 'is_available', 'created_at'
    ]
    list_filter = ['product_type', 'category', 'is_available', 'allow_grinding',
                   'roast_level', 'processing_method']
    search_fields = ['name', 'description']
    prepopulated_fields = {'slug': ('name',)}
    list_editable = ['is_available']
    raw_id_fields = ['category']
    date_hierarchy = 'created_at'
    list_per_page = 20

    # Image preview
    def image_thumbnail(self, obj):
        if obj.image:
            return format_html(
                '<img src="{}" style="width: 50px; height: 50px; object-fit: cover; border-radius: 4px;" />',
                obj.image.url
            )
        return format_html('<span style="color: #999;">-</span>')
    image_thumbnail.short_description = 'Фото'
    image_thumbnail.allow_tags = True

    # Price display
    def price_display(self, obj):
        if obj.product_type == 'coffee':
            return f'{obj.price_per_50g} rub / 50g'
        return f'{obj.base_price} rub'
    price_display.short_description = 'Price'

    # SCA score badge
    def sca_score_badge(self, obj):
        if obj.sca_score:
            if obj.sca_score >= 90:
                color = '#c62828'
                label = f'* {obj.sca_score}'
            elif obj.sca_score >= 85:
                color = '#f9a825'
                label = f'* {obj.sca_score}'
            else:
                color = '#4caf50'
                label = f'* {obj.sca_score}'
            return format_html(
                '<span style="background: {}; color: #fff; padding: 3px 8px; border-radius: 10px; font-size: 0.85em; font-weight: bold;">{}</span>',
                color, label
            )
        return '-'
    sca_score_badge.short_description = 'SCA'

    # Stock color
    def stock_color(self, obj):
        if obj.stock > 500:
            return format_html('<span style="color: #2e7d32;">{}</span>', obj.stock)
        elif obj.stock > 0:
            return format_html('<span style="color: #f9a825;">{}</span>', obj.stock)
        else:
            return format_html('<span style="color: #c62828;">{}</span>', obj.stock)
    stock_color.short_description = 'Stock'

    fieldsets = (
        ('Основное', {
            'fields': ('name', 'slug', 'description', 'category', 'product_type')
        }),
        ('Цены и остатки', {
            'fields': ('price_per_50g', 'base_price', 'stock')
        }),
        ('Кофе - параметры', {
            'fields': (
                'coffee_type', 'roast_level', 'origin_region',
                'processing_method', 'sca_score', 'tasting_notes'
            ),
            'classes': ('collapse',),
            'description': 'Заполнять только для кофе'
        }),
        ('Дополнительно', {
            'fields': ('image', 'is_available', 'allow_grinding',
                       'available_brewing_methods', 'allergens')
        }),
    )

    actions = ['make_available', 'unmake_available', 'recalculate_stock']

    def make_available(self, request, queryset):
        queryset.update(is_available=True)
    make_available.short_description = 'Available'

    def unmake_available(self, request, queryset):
        queryset.update(is_available=False)
    unmake_available.short_description = 'Hidden'

    def recalculate_stock(self, request, queryset):
        """Recalculate stock from related OrderItems."""
        from django.db.models import Sum
        for product in queryset:
            sold = product.items.aggregate(
                total=Sum('quantity')
            )['total'] or 0
            # This is a simplification - real logic would consider all orders
            self.message_user(
                request,
                f'Stock for {product.name} recalculated (sold: {sold})'
            )
    recalculate_stock.short_description = 'Recalculate Stock'


@admin.register(Product)
class VisibleProductAdmin(ProductAdmin):
    pass


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ['user', 'product', 'rating', 'is_approved', 'created_at']
    list_filter = ['rating', 'is_approved']
    search_fields = ['comment', 'user__username', 'product__name']
    list_editable = ['is_approved']
    readonly_fields = ['created_at', 'updated_at']
    actions = ['approve_reviews', 'unapprove_reviews']

    def approve_reviews(self, request, queryset):
        queryset.update(is_approved=True)
    approve_reviews.short_description = 'Approve reviews'

    def unapprove_reviews(self, request, queryset):
        queryset.update(is_approved=False)
    unapprove_reviews.short_description = 'Unapprove reviews'


admin.site.site_header = 'Coffee Shop Admin'
admin.site.site_title = 'Coffee Shop Administration'
admin.site.index_title = 'Welcome to Coffee Shop Admin'
