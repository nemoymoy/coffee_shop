"""Service for managing Yandex Delivery merchant accounts."""
import os
import logging
from datetime import timedelta
from django.conf import settings
from django.utils import timezone
from django.db import transaction

from coffee_shop.apps.orders.models import MerchantAccount

logger = logging.getLogger(__name__)


class MerchantAccountService:
    """Сервис для управления аккаунтами мерчантов Яндекс Доставки."""

    @staticmethod
    def get_active_merchant() -> MerchantAccount | None:
        """Получить активный аккаунт мерчанта."""
        try:
            return MerchantAccount.objects.filter(is_active=True).first()
        except MerchantAccount.DoesNotExist:
            return None

    @staticmethod
    def get_access_token() -> str | None:
        """Получить активный access_token с автообновлением."""
        merchant = MerchantAccountService.get_active_merchant()
        if not merchant:
            # Fallback на токен из настроек
            token = getattr(settings, 'YANDEX_DELIVERY_TOKEN', '')
            if token:
                return token
            return None

        # Если токен истёк, пробуем обновить
        if merchant.is_token_expired and merchant.refresh_token:
            refreshed = MerchantAccountService.refresh_token(merchant)
            if refreshed:
                return merchant.access_token

        return merchant.access_token if merchant.access_token else None

    @staticmethod
    def refresh_token(merchant: MerchantAccount) -> bool:
        """Обновить токен через refresh_token."""
        if not merchant.refresh_token:
            logger.warning('Нет refresh_token для мерчанта %s', merchant.pk)
            return False

        try:
            from coffee_shop.apps.orders.services.yandex_oauth import YandexOAuth

            oauth = YandexOAuth()
            oauth._refresh_token = merchant.refresh_token
            result = oauth.do_refresh_token()

            if 'error' in result:
                logger.error('Ошибка обновления токена: %s', result['error'])
                return False

            with transaction.atomic():
                merchant.access_token = result.get('access_token', merchant.access_token)
                merchant.refresh_token = result.get('refresh_token', merchant.refresh_token)
                expires_in = result.get('expires_in', 3600)
                merchant.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
                merchant.save(update_fields=[
                    'access_token', 'refresh_token', 'token_expires_at', 'updated_at'
                ])

            logger.info('Токен мерчанта %s обновлён', merchant.pk)
            return True

        except Exception as e:
            logger.error('Ошибка при обновлении токена: %s', e)
            return False

    @staticmethod
    def create_or_update(
        access_token: str,
        refresh_token: str = None,
        yandex_account_id: str = None,
        merchant_id: str = None,
        expires_in: int = 3600,
    ) -> MerchantAccount:
        """Создать или обновить аккаунт мерчанта."""
        from django.utils import timezone

        merchant = MerchantAccountService.get_active_merchant()

        if merchant:
            with transaction.atomic():
                merchant.access_token = access_token
                merchant.refresh_token = refresh_token or merchant.refresh_token
                merchant.yandex_account_id = yandex_account_id or merchant.yandex_account_id
                merchant.merchant_id = merchant_id or merchant.merchant_id
                merchant.token_expires_at = timezone.now() + timedelta(seconds=expires_in)
                merchant.is_active = True
                merchant.save()
            return merchant
        else:
            return MerchantAccount.objects.create(
                is_active=True,
                access_token=access_token,
                refresh_token=refresh_token,
                yandex_account_id=yandex_account_id,
                merchant_id=merchant_id,
                token_expires_at=timezone.now() + timedelta(seconds=expires_in),
            )

    @staticmethod
    def set_token_manually(token: str, merchant_id: str = None) -> MerchantAccount:
        """Установить токен вручную (для варианта B)."""
        from coffee_shop.apps.orders.services.yandex_oauth import YandexOAuth

        oauth = YandexOAuth()
        oauth.access_token = token
        yandex_account_id = oauth.get_yandex_account()

        # Для прямого токена refresh_token может не быть
        # Получим merchant_id если указан
        actual_merchant_id = merchant_id or getattr(settings, 'YANDEX_DELIVERY_MERCHANT_ID', '')

        return MerchantAccountService.create_or_update(
            access_token=token,
            yandex_account_id=yandex_account_id,
            merchant_id=actual_merchant_id,
            expires_in=86400 * 30,  # 30 дней для прямого токена
        )

    @staticmethod
    def test_connection(token: str) -> dict:
        """Проверить соединение с Яндекс Доставкой."""
        try:
            from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService

            service = YandexDeliveryService(access_token=token)
            info = service.get_merchant_info()
            return {
                'success': info.get('success', False),
                'merchant_id': info.get('merchant_id', ''),
                'error': info.get('error', ''),
            }
        except Exception as e:
            return {
                'success': False,
                'merchant_id': '',
                'error': str(e),
            }
