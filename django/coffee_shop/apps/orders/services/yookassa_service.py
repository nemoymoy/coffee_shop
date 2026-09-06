"""YooKassa (ЮКасса) payment gateway integration using official yookassa package."""
import hmac
import hashlib
import base64
from decimal import Decimal
from typing import Optional

from django.conf import settings
from yookassa import Configuration, Payment, Refund
from yookassa.domain.notification import (
    WebhookNotificationEventType,
    WebhookNotificationFactory,
)


class YooKassaService:
    """Сервис для работы с платёжной шлюзом ЮКасса (YooKassa) через официальный SDK."""

    def __init__(self):
        self._configure()

    def _configure(self):
        """Конфигурирует SDK ЮКасса."""
        shop_id = getattr(settings, 'YOOKASSA_SHOP_ID', '')
        secret_key = getattr(settings, 'YOOKASSA_SECRET_KEY', '')

        if shop_id and secret_key:
            Configuration.configure(shop_id, secret_key)

    def is_configured(self) -> bool:
        """Проверка, что сервис настроен."""
        shop_id = getattr(settings, 'YOOKASSA_SHOP_ID', '')
        secret_key = getattr(settings, 'YOOKASSA_SECRET_KEY', '')
        return bool(shop_id and secret_key)

    def create_payment(
        self,
        order_number: str,
        amount: Decimal,
        description: str,
        confirm_type: str = "redirect",
        return_url: Optional[str] = None,
    ) -> dict:
        """
        Создаёт платёж через ЮКассу.

        Args:
            order_number: Номер заказа в системе
            amount: Сумма платежа
            description: Описание платежа
            confirm_type: Тип подтверждения ('redirect' или 'qr')
            return_url: URL возврата (только для confirm_type='redirect')

        Returns:
            {
                'success': True,
                'payment_id': '...',
                'confirmation_url': '...',
                'amount': '...',
            }
            или {'success': False, 'error': '...'}
        """
        if not self.is_configured():
            return {
                "success": True,
                "payment_id": f"mock-{order_number}",
                "confirmation_url": f"{getattr(settings, 'SITE_URL', 'http://localhost:8000')}/pay/mock/{order_number}/",
                "amount": str(amount),
                "mock": True,
            }

        try:
            payment = Payment.create({
                "amount": {
                    "value": str(amount),
                    "currency": "RUB",
                },
                "confirmation": {
                    "type": confirm_type,
                    "return_url": return_url or getattr(
                        settings, 'YOOKASSA_RETURN_URL', ''
                    ),
                },
                "capture": True,
                "description": description,
                "metadata": {
                    "order_number": order_number,
                },
            })

            return {
                "success": True,
                "payment_id": payment.id,
                "confirmation_url": payment.confirmation.confirmation_url,
                "amount": str(payment.amount.value),
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def get_payment_status(self, payment_id: str) -> dict:
        """
        Получает статус платежа.

        Args:
            payment_id: ID платежа в ЮКассе

        Returns:
            {
                'success': True,
                'status': 'pending'|'confirmed'|'cancelled',
                'amount': '...',
                'paid': True|False,
            }
            или {'success': False, 'error': '...'}
        """
        if not self.is_configured():
            return {
                "success": True,
                "status": "confirmed",
                "paid": True,
                "mock": True,
            }

        try:
            payment = Payment.find_one(payment_id)

            return {
                "success": True,
                "status": payment.status,
                "amount": payment.amount.value,
                "paid": payment.paid,
                "metadata": payment.metadata,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def refund_payment(
        self, payment_id: str, amount: Optional[Decimal] = None
    ) -> dict:
        """
        Создаёт возврат.

        Args:
            payment_id: ID платежа в ЮКассе
            amount: Сумма возврата (если None — полный возврат)

        Returns:
            {
                'success': True,
                'refund_id': '...',
                'amount': '...',
            }
            или {'success': False, 'error': '...'}
        """
        if not self.is_configured():
            return {
                "success": True,
                "refund_id": f"mock-refund-{payment_id}",
                "mock": True,
            }

        try:
            refund_payload = {
                "payment_id": payment_id,
                "description": f"Возврат по заказу {payment_id}",
            }
            if amount:
                refund_payload["amount"] = {
                    "value": str(amount),
                    "currency": "RUB",
                }

            refund = Refund.create(refund_payload)

            return {
                "success": True,
                "refund_id": refund.id,
                "amount": refund.amount.value,
            }

        except Exception as e:
            return {"success": False, "error": str(e)}

    def verify_webhook(self, payload: dict, signature: str) -> bool:
        """
        Проверяет подпись webhook от ЮКассы.

        ЮКасса отправляет HMAC-SHA256 подпись в заголовке
        X-YooMoney-Signature. Подписывает строку вида:
        {request_body}

        Args:
            payload: Тело webhook (JSON dict)
            signature: Значение заголовка X-YooMoney-Signature

        Returns:
            True если подпись валидна
        """
        if not self.is_configured():
            return True  # В dev режиме пропускаем

        webhook_secret = getattr(
            settings, 'YOOKASSA_WEBHOOK_SECRET',
            getattr(settings, 'YOOKASSA_SECRET_KEY', '')
        )

        raw_body = base64.b64encode(
            str(payload).encode()
        ).decode()

        expected = hmac.new(
            webhook_secret.encode(),
            raw_body.encode(),
            hashlib.sha256,
        ).hexdigest()

        return hmac.compare_digest(expected, signature)

    def process_webhook(self, payload: dict) -> dict:
        """
        Обрабатывает webhook от ЮКассы.

        Поддерживаемые события:
        - payment.succeeded
        - payment.canceled

        Args:
            payload: Данные webhook (JSON dict)

        Returns:
            {
                'status': 'paid'|'failed'|'unknown',
                'payment_id': '...',
                'order_number': '...',
            }
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
                    "status": "paid",
                    "payment_id": payment_object.id,
                    "order_number": order_number,
                    "amount": payment_object.amount.value,
                    "paid": payment_object.paid,
                }

            elif event == WebhookNotificationEventType.PAYMENT_CANCELED:
                return {
                    "status": "failed",
                    "payment_id": payment_object.id,
                    "order_number": order_number,
                }

            return {
                "status": "unknown",
                "event_type": event,
                "payment_id": payment_object.id,
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}
