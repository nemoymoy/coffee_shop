from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class OrderItem(models.Model):
    """Позиция заказа."""

    COFFEE_FORM_BEANS = 'beans'
    COFFEE_FORM_GROUND = 'ground'
    COFFEE_FORM_CHOICES = [
        (COFFEE_FORM_BEANS, 'В зёрнах'),
        (COFFEE_FORM_GROUND, 'Молотый'),
    ]

    TURKA = 'turka'
    ESPRESSO = 'espresso'
    GEYSER = 'geyser'
    PUROVER = 'pourover'
    SYYPON = 'siphon'
    AEROPRESS = 'aeropress'
    CHEX = 'chemex'
    FRENCH_PRESS = 'french_press'
    CAPPING = 'capping'
    FILTER_MACHINE = 'filter_machine'

    BREWING_METHOD_CHOICES = [
        (TURKA, 'Турка (джезва)'),
        (ESPRESSO, 'Эспрессо-машина'),
        (GEYSER, 'Гейзер (мокка)'),
        (PUROVER, 'Пуровер (воронка)'),
        (SYYPON, 'Сифон (габет)'),
        (AEROPRESS, 'Аэропресс'),
        (CHEX, 'Кемекс'),
        (FRENCH_PRESS, 'Френч-пресс'),
        (CAPPING, 'Помол на каппинг'),
        (FILTER_MACHINE, 'Фильтр-машина'),
    ]

    order = models.ForeignKey(
        'orders.Order',
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='Заказ'
    )
    product = models.ForeignKey(
        'catalog.Product',
        on_delete=models.PROTECT,
        verbose_name='Товар'
    )
    quantity = models.IntegerField(validators=[MinValueValidator(1)], verbose_name='Количество')
    unit_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Цена за единицу'
    )

    # Coffee params
    coffee_weight_grams = models.IntegerField(
        null=True,
        blank=True,
        verbose_name='Вес кофе (г)'
    )
    coffee_form = models.CharField(
        max_length=10,
        choices=COFFEE_FORM_CHOICES,
        null=True,
        blank=True,
        verbose_name='Форма кофе'
    )
    brewing_method = models.CharField(
        max_length=20,
        choices=BREWING_METHOD_CHOICES,
        null=True,
        blank=True,
        verbose_name='Способ заваривания'
    )

    package = models.ForeignKey(
        'orders.Package',
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        verbose_name='Тара'
    )
    weight_grams = models.IntegerField(
        verbose_name='Вес содержимого (г)',
        default=0
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создана')

    class Meta:
        indexes = [
            models.Index(fields=['order', 'product']),
        ]

    def __str__(self):
        return f'{self.product.name} x{self.quantity}'

    @property
    def total_price(self):
        return self.quantity * self.unit_price
