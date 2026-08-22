import re
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator
from django.db import models


class Product(models.Model):
    """Товар кофейни. Для кофе — полная карточка с параметрами зерна."""

    PRODUCT_TYPE_COFFEE = 'coffee'
    PRODUCT_TYPE_OTHER = 'other'
    PRODUCT_TYPES = [
        (PRODUCT_TYPE_COFFEE, 'Кофе'),
        (PRODUCT_TYPE_OTHER, 'Не кофе'),
    ]

    ROAST_CHOICES = [
        ('light', 'Светлая'),
        ('medium', 'Средняя'),
        ('medium-dark', 'Средне-тёмная'),
        ('dark', 'Тёмная'),
        ('dark-roast', 'Очень тёмная'),
    ]

    PROCESSING_CHOICES = [
        ('natural', 'Натуральная (natural)'),
        ('washed', 'Мытая (washed)'),
        ('honey', 'Медовая (honey)'),
        ('anaerobic', 'Анаэробная (anaerobic)'),
        ('other', 'Другая'),
    ]

    BREWING_CHOICES = [
        ('turka', 'Турка (джезва)'),
        ('espresso', 'Эспрессо-машина'),
        ('siphon', 'Сифон (габет)'),
        ('pourover', 'Пуровер (воронка)'),
        ('aeropress', 'Аэропресс'),
        ('chemex', 'Кемекс'),
        ('french_press', 'Френч-пресс'),
        ('capping', 'Помол на каппинг'),
        ('filter_machine', 'Фильтр-машина'),
    ]

    name = models.CharField(max_length=200, verbose_name='Название')
    slug = models.SlugField(max_length=200, unique=True, verbose_name='URL-адрес')
    description = models.TextField(blank=True, verbose_name='Описание')
    category = models.ForeignKey(
        'catalog.Category',
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='products',
        verbose_name='Категория'
    )
    product_type = models.CharField(
        max_length=10,
        choices=PRODUCT_TYPES,
        default=PRODUCT_TYPE_COFFEE,
        verbose_name='Тип товара'
    )
    price_per_50g = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name='Цена за 50 г'
    )
    base_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        validators=[MinValueValidator(0)],
        verbose_name='Базовая цена (для не кофе)',
        default=0
    )
    stock = models.IntegerField(default=0, verbose_name='Остаток на складе (г)')
    image = models.ImageField(
        upload_to='products/',
        blank=True,
        null=True,
        verbose_name='Изображение'
    )
    is_available = models.BooleanField(default=True, verbose_name='Доступен')
    allow_grinding = models.BooleanField(default=False, verbose_name='Доступен помол')
    available_brewing_methods = models.JSONField(
        default=list,
        blank=True,
        verbose_name='Доступные способы заваривания'
    )
    allergens = models.TextField(blank=True, verbose_name='Аллергены')

    # --- Поля для кофе ---
    coffee_type = models.CharField(
        max_length=100,
        blank=True,
        verbose_name='Сорт (арабика/робуста/микс, пача, бурбон и т.д.)'
    )
    roast_level = models.CharField(
        max_length=20,
        choices=ROAST_CHOICES,
        blank=True,
        verbose_name='Обжарка'
    )
    origin_region = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Регион (страна + ферма/кооператив)'
    )
    processing_method = models.CharField(
        max_length=50,
        choices=PROCESSING_CHOICES,
        blank=True,
        verbose_name='Обработка'
    )
    sca_score = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(100)],
        verbose_name='Рейтинг SCA'
    )
    tasting_notes = models.TextField(
        blank=True,
        verbose_name='Характеристика (вкус/аромат/тело/кислотность)'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлена')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['slug']),
            models.Index(fields=['category', 'is_available']),
            models.Index(fields=['stock']),
            models.Index(fields=['roast_level']),
            models.Index(fields=['sca_score']),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        # Валидация: если молотый доступен — brewing_methods не пустой
        if self.allow_grinding and not self.available_brewing_methods:
            raise ValidationError({
                'available_brewing_methods': (
                    'Укажите способы заваривания, если разрешён помол'
                )
            })

    @property
    def available_stock(self):
        """
        Доступный остаток товара (stock - зарезервировано).
        Используется в шаблонах как {{ product.available_stock }}.
        """
        try:
            from coffee_shop.apps.orders.services.stock_service import StockService
            return StockService.get_available_stock(self)
        except Exception:
            return self.stock

    @property
    def is_in_stock(self):
        return self.available_stock > 0

    @property
    def max_weight_grams(self):
        return self.available_stock
