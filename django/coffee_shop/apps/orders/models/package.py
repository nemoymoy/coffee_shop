"""Package model for Yandex Cargo delivery dimensions."""
from django.db import models


class Package(models.Model):
    """Тара: габариты и вес коробки в зависимости от веса содержимого."""

    WEIGHT_RANGE_CHOICES = [
        ('light', 'до 100 г'),
        ('medium', '100–500 г'),
        ('heavy', '500 г – 2 кг'),
        ('xl', '2–5 кг'),
        ('xxl', '5–10 кг'),
    ]

    weight_range = models.CharField(
        max_length=20,
        choices=WEIGHT_RANGE_CHOICES,
        unique=True,
        verbose_name='Диапазон веса'
    )
    length = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        verbose_name='Длина (м)'
    )
    width = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        verbose_name='Ширина (м)'
    )
    height = models.DecimalField(
        max_digits=5,
        decimal_places=3,
        verbose_name='Высота (м)'
    )
    tare_weight = models.DecimalField(
        max_digits=6,
        decimal_places=3,
        verbose_name='Вес коробки (кг)'
    )

    class Meta:
        verbose_name = 'Тара'
        verbose_name_plural = 'Тары'
        ordering = ['weight_range']

    def __str__(self):
        return f'Тара {self.weight_range} ({self.length}x{self.width}x{self.height} м)'

    @classmethod
    def for_weight(cls, weight_grams):
        """Возвращает Package по весу товара в граммах."""
        if weight_grams <= 100:
            return cls.objects.get(weight_range='light')
        elif weight_grams <= 500:
            return cls.objects.get(weight_range='medium')
        elif weight_grams <= 2000:
            return cls.objects.get(weight_range='heavy')
        elif weight_grams <= 5000:
            return cls.objects.get(weight_range='xl')
        else:
            return cls.objects.get(weight_range='xxl')

    @property
    def total_weight(self):
        return self.tare_weight  # в кг
