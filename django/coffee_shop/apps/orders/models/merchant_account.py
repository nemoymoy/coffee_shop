"""Merchant account for Yandex Delivery integration."""
from django.db import models


class MerchantAccount(models.Model):
    """Аккаунт мерчанта для Яндекс Доставки."""

    is_active = models.BooleanField(default=True, verbose_name='Активен')
    access_token = models.CharField(max_length=500, blank=True, verbose_name='Access Token')
    refresh_token = models.CharField(max_length=500, blank=True, verbose_name='Refresh Token')
    yandex_account_id = models.CharField(max_length=100, blank=True, verbose_name='Yandex Account ID')
    merchant_id = models.CharField(max_length=100, blank=True, verbose_name='Merchant ID')
    token_expires_at = models.DateTimeField(null=True, blank=True, verbose_name='Истекает токен')
    created_at = models.DateTimeField(auto_now_add=True, verbose_name='Создан')
    updated_at = models.DateTimeField(auto_now=True, verbose_name='Обновлён')

    class Meta:
        verbose_name = 'Аккаунт мерчанта'
        verbose_name_plural = 'Аккаунты мерчантов'
        ordering = ['-created_at']

    def __str__(self):
        status = 'Active' if self.is_active else 'Inactive'
        return f'{status} — {self.merchant_id or "Not configured"}'

    @property
    def is_token_expired(self) -> bool:
        """Проверка, истёк ли токен."""
        if not self.token_expires_at:
            return False
        from django.utils import timezone
        return timezone.now() >= self.token_expires_at
