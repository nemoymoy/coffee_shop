from django.db import models
from django.conf import settings


class Order(models.Model):
    """Заказ клиента."""

    STATUS_CHOICES = [
        ('new', 'Новый'),
        ('awaiting_payment', 'Ожидает оплаты'),
        ('in_progress', 'В обработке'),
        ('ready', 'Готов'),
        ('delivered', 'Доставлен'),
        ('cancelled', 'Отменён'),
    ]

    PAYMENT_METHOD_CHOICES = [
        ('online', 'Онлайн'),
        ('cash', 'При получении'),
    ]

    DELIVERY_METHOD_CHOICES = [
        ('pickup', 'Самовывоз'),
        ('delivery', 'Доставка'),
    ]

    YANDEX_DELIVERY_TYPE_CHOICES = [
        ('courier', 'Курьер'),
        ('pvz', 'Пункт выдачи (ПВЗ)'),
        ('postomat', 'Постомат'),
    ]

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name='Пользователь'
    )
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='new',
        verbose_name='Статус'
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name='Итого'
    )
    yookassa_payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID платежа в ЮКассе'
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PAYMENT_METHOD_CHOICES,
        verbose_name='Способ оплаты'
    )
    delivery_method = models.CharField(
        max_length=10,
        choices=DELIVERY_METHOD_CHOICES,
        verbose_name='Способ получения'
    )

    first_name = models.CharField(max_length=100, verbose_name='Имя')
    last_name = models.CharField(max_length=100, verbose_name='Фамилия')
    phone = models.CharField(max_length=20, verbose_name='Телефон')
    email = models.EmailField(verbose_name='Email')

    comment = models.TextField(blank=True, verbose_name='Комментарий')

    # Delivery
    delivery_address = models.TextField(
        blank=True,
        verbose_name='Адрес доставки'
    )
    delivery_date = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Дата доставки'
    )
    delivery_time = models.TimeField(
        null=True,
        blank=True,
        verbose_name='Время доставки'
    )

    # Yandex Delivery integration
    yandex_access_token = models.CharField(
        max_length=500,
        blank=True,
        null=True,
        verbose_name='OAuth токен Яндекс Доставки'
    )
    yandex_order_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID заказа в Яндекс Доставке'
    )
    yandex_delivery_type = models.CharField(
        max_length=20,
        choices=YANDEX_DELIVERY_TYPE_CHOICES,
        blank=True,
        verbose_name='Тип Яндекс Доставки'
    )
    tracking_number = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='Трек-номер'
    )
    delivery_status = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Статус доставки'
    )
    delivery_cost = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=0,
        verbose_name='Стоимость доставки'
    )

    reserved_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name='Зарезервировано'
    )

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status']),
            models.Index(fields=['user', 'status']),
            models.Index(fields=['created_at']),
        ]

    def __str__(self):
        return f'Заказ #{self.pk} — {self.last_name} {self.first_name}'

    @property
    def full_name(self):
        return f'{self.last_name} {self.first_name}'
