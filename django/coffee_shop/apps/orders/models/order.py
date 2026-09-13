from django.db import models
from django.conf import settings
from django.utils import timezone


class Order(models.Model):
    """Заказ клиента."""

    class Status(models.TextChoices):
        NEW = "new", "Новый"
        AWAITING_PAYMENT = "awaiting_payment", "Ожидает оплаты"
        PAID = "in_progress", "Оплачен"
        READY = "ready", "Готов"
        DELIVERED = "delivered", "Доставлен"
        CANCELED = "cancelled", "Отменён"
        REFUNDED = "refunded", "Возврат"

    class PaymentMethod(models.TextChoices):
        ONLINE = "online", "Онлайн"
        CASH = "cash", "При получении"

    class DeliveryMethod(models.TextChoices):
        PICKUP = "pickup", "Самовывоз"
        DELIVERY = "delivery", "Доставка"

    class DeliveryType(models.TextChoices):
        COURIER = "courier", "Курьер"
        PVZ = "pickup", "ПВЗ"
        POSTAMAT = "postamat", "Постомат"

    order_number = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="Номер заказа"
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.NEW,
        verbose_name="Статус"
    )
    total_amount = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Итого"
    )
    payment_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name="ID платежа в платёжной системе"
    )
    payment_method = models.CharField(
        max_length=10,
        choices=PaymentMethod.choices,
        verbose_name="Способ оплаты"
    )
    delivery_method = models.CharField(
        max_length=10,
        choices=DeliveryMethod.choices,
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

    # Yandex Cargo API integration
    yandex_order_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID заказа в Cargo API'
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
    delivery_type = models.CharField(
        max_length=20,
        choices=DeliveryType.choices,
        default=DeliveryType.COURIER,
        verbose_name='Тип доставки'
    )
    pvz_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID ПВЗ/постомата (Yandex)'
    )
    destination_coords = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name='Координаты доставки [lon,lat]'
    )

    # Идемпотентность (operator_request_id)
    client_order_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID идемпотентности (operator_request_id)'
    )

    # Интервал доставки (Other Day API)
    delivery_interval_from = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Интервал доставки от'
    )
    delivery_interval_to = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name='Интервал доставки до'
    )

    # Получатель
    recipient_name = models.CharField(
        max_length=200,
        blank=True,
        verbose_name='Имя получателя'
    )
    recipient_phone = models.CharField(
        max_length=20,
        blank=True,
        verbose_name='Телефон получателя'
    )

    # Тип API Яндекс Доставки
    DELIVERY_API_TYPE_CHOICES = (
        ('express', 'Express (день-в-день)'),
        ('other_day', 'Other Day (выбранный интервал)'),
    )
    delivery_api_type = models.CharField(
        max_length=20,
        choices=DELIVERY_API_TYPE_CHOICES,
        default='other_day',
        verbose_name='Тип API Яндекс Доставки'
    )

    # Для Express API
    express_claim_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID заявки Express API'
    )

    # Для Other Day API (ПВЗ/Постомат)
    yandex_offer_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        verbose_name='ID оффера Яндекс Доставки (Other Day API)'
    )

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='orders',
        verbose_name='Пользователь'
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
        return f'Заказ {self.order_number} — {self.get_status_display()}'

    @property
    def full_name(self):
        return f'{self.last_name} {self.first_name}'

    def save(self, *args, **kwargs):
        """Автоматически генерируем order_number при создании."""
        is_new = self.pk is None
        super().save(*args, **kwargs)
        if is_new and not self.order_number:
            # Генерируем order_number после присвоения pk
            self.order_number = f"ORD-{timezone.now().strftime('%Y%m%d')}-{self.pk:06d}"
            super().save(update_fields=['order_number'])
