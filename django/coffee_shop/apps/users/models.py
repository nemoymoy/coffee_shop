"""Personal data consent model for 152-FZ compliance."""
from django.db import models
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
