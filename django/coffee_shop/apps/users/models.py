"""Personal data consent model for 152-FZ compliance."""
import uuid

from django.db import models
from django.conf import settings
from django.utils import timezone
from datetime import timedelta

from django.contrib.auth.models import User


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
        return not self.is_used and not self.is_expired

    def __str__(self):
        return f'Email verification for {self.user.email}'
