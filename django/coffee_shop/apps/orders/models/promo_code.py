from django.db import models


class PromoCode(models.Model):
    """Промокод на скидку."""

    DISCOUNT_TYPE_PERCENT = 'percent'
    DISCOUNT_TYPE_FIXED = 'fixed'
    DISCOUNT_TYPES = [
        (DISCOUNT_TYPE_PERCENT, 'Процент'),
        (DISCOUNT_TYPE_FIXED, 'Фиксированная сумма'),
    ]

    code = models.CharField(max_length=50, unique=True, verbose_name='Код')
    discount_type = models.CharField(
        max_length=10,
        choices=DISCOUNT_TYPES,
        verbose_name='Тип скидки'
    )
    discount_value = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name='Значение скидки'
    )
    max_uses = models.IntegerField(default=0, verbose_name='Лимит использований (0 = безлимит)')
    used_count = models.IntegerField(default=0, verbose_name='Использовано')
    valid_from = models.DateTimeField(verbose_name='Действует с')
    valid_to = models.DateTimeField(verbose_name='Действует до')
    is_active = models.BooleanField(default=True, verbose_name='Активен')

    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Промокод'
        verbose_name_plural = 'Промокоды'

    def __str__(self):
        return self.code

    @property
    def is_valid(self):
        from django.utils import timezone
        now = timezone.now()
        return (
            self.is_active and
            self.valid_from <= now <= self.valid_to and
            (self.max_uses == 0 or self.used_count < self.max_uses)
        )

    @property
    def remaining_uses(self):
        if self.max_uses == 0:
            return 0  # безлимит
        return max(0, self.max_uses - self.used_count)
