"""Personal data consent model for 152-FZ compliance."""
import uuid

from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from django.contrib.auth.models import User


class UserProfile(models.Model):
    """Дополнительная информация о пользователе."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='profile',
        verbose_name='Пользователь',
    )
    phone = models.CharField(
        max_length=20,
        blank=True,
        default='',
        verbose_name='Телефон',
    )
    birth_date = models.DateField(
        null=True,
        blank=True,
        verbose_name='Дата рождения',
    )
    GENDER_CHOICES = [
        ('M', 'Мужской'),
        ('F', 'Женский'),
    ]
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        blank=True,
        default='',
        verbose_name='Пол',
    )

    class Meta:
        verbose_name = 'Профиль пользователя'
        verbose_name_plural = 'Профили пользователей'

    def __str__(self):
        return f'Profile of {self.user.get_full_name() or self.user.username}'


class PersonalDataConsent(models.Model):
    """
    Модель для хранения подтверждений согласия на обработку персональных данных.
    Реализация соответствует требованиям 152-ФЗ «О персональных данных».
    """

    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='personal_data_consent',
        verbose_name='Пользователь',
    )
    # Версия согласия для учёта изменений текста
    version = models.CharField(
        max_length=10,
        default='1.0',
        verbose_name='Версия согласия',
    )
    # MD5-хэш текста согласия на момент предоставления (для аудита)
    content_hash = models.CharField(
        max_length=64,
        verbose_name='Хэш текста согласия',
    )
    # Дата и время предоставления согласия
    consented_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата предоставления',
    )
    # IP-адрес для аудита
    ip_address = models.GenericIPAddressField(
        null=True,
        blank=True,
        verbose_name='IP-адрес',
    )
    # User-Agent браузера для аудита
    user_agent = models.TextField(
        blank=True,
        default='',
        max_length=1000,
        verbose_name='User-Agent',
    )

    class Meta:
        ordering = ['-consented_at']
        verbose_name = 'Согласие на обработку ПД'
        verbose_name_plural = 'Согласия на обработку ПД'
        indexes = [
            models.Index(fields=['user', 'version']),
        ]

    def __str__(self):
        return f'Согласие пользователя {self.user.get_full_name() or self.user.username} (v{self.version})'


class UserEmailVerification(models.Model):
    """Токен подтверждения email пользователя."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='email_verification',
        verbose_name='Пользователь',
    )
    token = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        verbose_name='Токен подтверждения',
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Дата создания',
    )
    expires_at = models.DateTimeField(
        verbose_name='Дата истечения',
    )
    is_used = models.BooleanField(
        default=False,
        verbose_name='Использован',
    )

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Подтверждение email'
        verbose_name_plural = 'Подтверждения email'

    def save(self, *args, **kwargs):
        if not self.expires_at:
            self.expires_at = timezone.now() + timedelta(hours=24)
        super().save(*args, **kwargs)

    @property
    def is_expired(self):
        return timezone.now() >= self.expires_at

    @property
    def is_valid(self):
        """Токен валиден для использования (не использован и не истёк)."""
        return not self.is_used and not self.is_expired

    @property
    def is_email_verified(self):
        """Email подтверждён (токен использован и не истёк)."""
        return self.is_used and not self.is_expired

    def __str__(self):
        return f'Email verification for {self.user.email}'


class DeliveryAddress(models.Model):
    """
    Сохранённый адрес доставки пользователя.

    Формат хранения соответствует требованиям Яндекс Доставки:
    - full_address — полный адрес (из геокодера Яндекс)
    - coordinates — координаты [lon,lat] для расчёта стоимости доставки
    - label — метка пользователя ("Дом", "Офис", "Дача")
    - apartment — номер квартиры/офиса
    - is_default — адрес по умолчанию
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='delivery_addresses',
        verbose_name='Пользователь',
    )
    label = models.CharField(
        max_length=50,
        verbose_name='Метка',
        help_text='Например: Дом, Офис, Дача',
    )
    full_address = models.CharField(
        max_length=500,
        verbose_name='Полный адрес',
        help_text='Полный адрес из геокодера Яндекс (например: Самара ул Революционная 3)',
    )
    coordinates = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='Координаты [lon,lat]',
        help_text='Координаты адреса в формате longitude,latitude',
    )
    apartment = models.CharField(
        max_length=50,
        blank=True,
        default='',
        verbose_name='Квартира/офис',
    )
    is_default = models.BooleanField(
        default=False,
        verbose_name='По умолчанию',
        help_text='Используется по умолчанию при оформлении заказа',
    )

    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name='Создан',
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name='Обновлён',
    )

    class Meta:
        ordering = ['-is_default', '-created_at']
        verbose_name = 'Адрес доставки'
        verbose_name_plural = 'Адреса доставки'
        indexes = [
            models.Index(fields=['user', 'is_default']),
        ]

    def __str__(self):
        return f'{self.user.get_full_name() or self.user.username}: {self.label} ({self.full_address})'

    def save(self, *args, **kwargs):
        """Убедимся, что только один адрес пользователя является дефолтным."""
        if self.is_default:
            DeliveryAddress.objects.filter(
                user=self.user,
                is_default=True
            ).exclude(pk=self.pk).update(is_default=False)
        super().save(*args, **kwargs)

    @property
    def display_address(self):
        """Формирование адреса для отображения в интерфейсе."""
        parts = [self.full_address]
        if self.apartment:
            parts.append(f'кв. {self.apartment}')
        return ' | '.join(parts)
