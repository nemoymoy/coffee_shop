"""YooKassa (ЮКасса) payment gateway integration using official yookassa package."""
import hmac
import hashlib
from decimal import Decimal
from logging import getLogger
from typing import Optional

from django.conf import settings
from yookassa import Configuration, Payment, Refund
from yookassa.domain.notification import (
    WebhookNotificationEventType,
    WebhookNotificationFactory,
)

logger = getLogger(__name__)


class YooKassaService:
    """Сервис для работы с платёжным шлюзом ЮКасса (YooKassa) через официальный SDK."""

    # Keys shared across _configure / is_configured / get_config_error
    _SHOP_ID_KEY = 'YOOKASSA_SHOP_ID'
    _SECRET_KEY_KEY = 'YOOKASSA_SECRET_KEY'
    _WEBHOOK_SECRET_KEY = 'YOOKASSA_WEBHOOK_SECRET'

    def __init__(self) -> None:
        self._configured = False
        self._configure()

    # ── Configuration ────────────────────────────────────────────────

    def _configure(self) -> None:
        """Configure the YooKassa SDK once (global singleton state)."""
        shop_id = getattr(settings, self._SHOP_ID_KEY, '')
        secret_key = getattr(settings, self._SECRET_KEY_KEY, '')

        if shop_id and secret_key:
            Configuration.configure(shop_id, secret_key)
            self._configured = True
        else:
            self._configured = False

    def _shop_id(self) -> str:
        return getattr(settings, self._SHOP_ID_KEY, '')

    def _secret_key(self) -> str:
        return getattr(settings, self._SECRET_KEY_KEY, '')

    def is_configured(self) -> bool:
        """Return ``True`` when required YooKassa credentials are present."""
        return bool(self._shop_id() and self._secret_key())

    def get_config_error(self) -> str:
        """Return a human-readable configuration error, or ``''`` if OK."""
        if not self._shop_id():
            return 'Не указан YOOKASSA_SHOP_ID'
        if not self._secret_key():
            return 'Не указан YOOKASSA_SECRET_KEY'
        return ''

    # ── Payment operations ───────────────────────────────────────────

    def create_payment(
        self,
        order_number: str,
        amount: Decimal,
        description: str,
        confirm_type: str = 'redirect',
        return_url: Optional[str] = None,
    ) -> dict:
        """
        Создаёт платёж через ЮКассу.

        Args:
            order_number: Номер заказа в системе.
            amount:       Сумма платежа.
            description:  Описание платежа.
            confirm_type: Тип подтверждения ('redirect' или 'qr').
            return_url:   URL возврата (только для confirm_type='redirect').

        Returns:
            dict с ключами success, payment_id, confirmation_url, amount
            (и mock=True в dev-режиме), либо {'success': False, 'error': ...}.
        """
        if not self.is_configured():
            site_url = getattr(settings, 'SITE_URL', 'http://localhost:8000')
            return {
                'success': True,
                'payment_id': f'mock-{order_number}',
                'confirmation_url': (
                    f'{site_url}/pay/mock/{order_number}/'
                ),
                'amount': str(amount),
                'mock': True,
            }

        try:
            payment = Payment.create({
                'amount': {
                    'value': str(amount),
                    'currency': 'RUB',
                },
                'confirmation': {
                    'type': confirm_type,
                    'return_url': return_url or getattr(
                        settings, 'YOOKASSA_RETURN_URL', ''
                    ),
                },
                'capture': True,
                'description': description,
                'metadata': {
                    'order_number': order_number,
                },
            })

            return {
                'success': True,
                'payment_id': payment.id,
                'confirmation_url': payment.confirmation.confirmation_url,
                'amount': str(payment.amount.value),
            }

        except Exception:
            logger.exception(
                'YooKassa create_payment failed for order=%s, amount=%s',
                order_number,
                amount,
            )
            return {'success': False, 'error': 'Не удалось создать платёж'}

    def get_payment_status(self, payment_id: str) -> dict:
        """
        Получает статус платежа.

        Returns:
            {'success': True, 'status': ..., 'paid': ..., ...}
            или {'success': False, 'error': ...}.
        """
        if not self.is_configured():
            return {
                'success': True,
                'status': 'confirmed',
                'paid': True,
                'mock': True,
            }

        try:
            payment = Payment.find_one(payment_id)

            return {
                'success': True,
                'status': payment.status,
                'amount': payment.amount.value,
                'paid': payment.paid,
                'metadata': payment.metadata,
            }

        except Exception:
            logger.exception(
                'YooKassa get_payment_status failed for payment_id=%s',
                payment_id,
            )
            return {'success': False, 'error': 'Не удалось получить статус платежа'}

    def refund_payment(
        self,
        payment_id: str,
        amount: Optional[Decimal] = None,
    ) -> dict:
        """
        Создаёт возврат (полный или частичный).

        Returns:
            {'success': True, 'refund_id': ..., 'amount': ...}
            или {'success': False, 'error': ...}.
        """
        if not self.is_configured():
            return {
                'success': True,
                'refund_id': f'mock-refund-{payment_id}',
                'mock': True,
            }

        try:
            refund_payload: dict = {
                'payment_id': payment_id,
                'description': f'Возврат по заказу {payment_id}',
            }
            if amount is not None:
                refund_payload['amount'] = {
                    'value': str(amount),
                    'currency': 'RUB',
                }

            refund = Refund.create(refund_payload)

            return {
                'success': True,
                'refund_id': refund.id,
                'amount': refund.amount.value,
            }

        except Exception:
            logger.exception(
                'YooKassa refund_payment failed for payment_id=%s, amount=%s',
                payment_id,
                amount,
            )
            return {'success': False, 'error': 'Не удалось создать возврат'}

    # ── Webhook handling ─────────────────────────────────────────────

    def verify_webhook(self, body: str, signature: str) -> bool:
        """
        Проверяет HMAC-SHA256 подпись webhook от ЮКассы.

        ЮКасса отправляет подпись в заголовке X-YooMoney-Signature.
        Подписывается строка: ``{body}\\n{secret_key}``.

        Args:
            body:      Тело webhook (исходная JSON-строка из request.body).
            signature: Значение заголовка X-YooMoney-Signature.

        Returns:
            ``True`` если подпись валидна.
        """
        if not self.is_configured():
            logger.debug('Webhook signature skipped — not configured (dev mode)')
            return True

        webhook_secret = getattr(
            settings, self._WEBHOOK_SECRET_KEY, self._secret_key()
        )

        message = f'{body}\n{webhook_secret}'
        expected = hmac.new(
            message.encode(), hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def process_webhook(self, payload: dict) -> dict:
        """
        Обрабатывает webhook от ЮКассы.

        Поддерживаемые события:
        - payment.succeeded
        - payment.canceled

        Args:
            payload: Данные webhook (JSON dict).

        Returns:
            dict с ключами status, payment_id, order_number (и amount при успехе).
        """
        try:
            notification = WebhookNotificationFactory().create(payload)
            event = notification.event
            payment_object = notification.object

            order_number = getattr(payment_object, 'metadata', {}).get(
                'order_number'
            )

            if event == WebhookNotificationEventType.PAYMENT_SUCCEEDED:
                return {
                    'status': 'paid',
                    'payment_id': payment_object.id,
                    'order_number': order_number,
                    'amount': payment_object.amount.value,
                    'paid': payment_object.paid,
                }

            if event == WebhookNotificationEventType.PAYMENT_CANCELED:
                return {
                    'status': 'failed',
                    'payment_id': payment_object.id,
                    'order_number': order_number,
                }

            logger.warning(
                'Unhandled YooKassa event type: %s, payment_id: %s',
                event,
                getattr(payment_object, 'id', None),
            )
            return {
                'status': 'unknown',
                'event_type': event,
                'payment_id': getattr(payment_object, 'id', None),
            }

        except Exception:
            logger.exception('YooKassa process_webhook failed for payload=%s', payload)
            return {'status': 'error', 'error': 'Не удалось обработать webhook'}
