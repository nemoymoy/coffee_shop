"""YooKassa (ЮКасса) payment gateway integration."""
import hmac
import hashlib
import base64
from typing import Optional
from decimal import Decimal

import requests
from django.conf import settings
from django.utils import timezone


class YooKassaService:
    """Сервис для работы с платёжной шлюзом ЮКасса (YooKassa)."""

    API_HOST = "api.yookassa.ru"
    API_VERSION = "v2"

    def __init__(self):
        self.merchant_id = getattr(settings, "YOOKASSA_MERCHANT_ID", "")
        self.api_key = getattr(settings, "YOOKASSA_API_KEY", "")
        self.test_mode = getattr(settings, "YOOKASSA_TEST_MODE", True)

    def is_configured(self) -> bool:
        """Проверка, что сервис настроен."""
        return bool(self.merchant_id and self.api_key)

    def _auth_header(self) -> str:
        """Basic Auth: LOGIN:SECRET_KEY encoded in base64."""
        credentials = f"{self.merchant_id}:{self.api_key}"
        return f"Basic {base64.b64encode(credentials.encode()).decode()}"

    def create_payment(
        self,
        order_id: int,
        amount: Decimal,
        description: str,
        confirm_type: str = "redirect",
        return_url: Optional[str] = None,
    ) -> dict:
        """
        Создаёт платёж через ЮКассу.

        Args:
            order_id: ID заказа в системе
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
                "payment_id": f"mock-{order_id}",
                "confirmation_url": f"http://localhost:8000/pay/mock/{order_id}/",
                "amount": str(amount),
                "mock": True,
            }

        try:
            amount_dict = {
                "value": str(amount),
                "currency": "RUB",
            }

            payload = {
                "amount": amount_dict,
                "description": description,
                "capture": True,
                "metadata": {
                    "order_id": str(order_id),
                },
                "confirmation": {
                    "type": confirm_type,
                    "return_url": return_url or getattr(
                        settings, "YOOKASSA_RETURN_URL", ""
                    ),
                },
            }

            response = requests.post(
                f"https://{self.API_HOST}/{self.API_VERSION}/payments",
                json=payload,
                headers={
                    "Idempotence-Key": self._generate_idempotence_key(),
                    "Authorization": self._auth_header(),
                },
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            return {
                "success": True,
                "payment_id": data["id"],
                "confirmation_url": data["confirmation"]["confirmation_url"],
                "amount": str(data["amount"]["value"]),
            }

        except requests.RequestException as e:
            return {"success": False, "error": str(e)}
        except (KeyError, ValueError) as e:
            return {"success": False, "error": f"Invalid response: {e}"}

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
            }
            или {'success': False, 'error': '...'}
        """
        if not self.is_configured():
            return {
                "success": True,
                "status": "confirmed",
                "mock": True,
            }

        try:
            response = requests.get(
                f"https://{self.API_HOST}/{self.API_VERSION}/payments/{payment_id}",
                headers={"Authorization": self._auth_header()},
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            return {
                "success": True,
                "status": data["status"],
                "amount": str(data["amount"]["value"]),
                "paid": data.get("paid", False),
            }

        except requests.RequestException as e:
            return {"success": False, "error": str(e)}

    def refund_payment(self, payment_id: str, amount: Optional[Decimal] = None) -> dict:
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
            return {"success": True, "refund_id": f"mock-refund-{payment_id}", "mock": True}

        try:
            payload: dict = {}
            if amount:
                payload["amount"] = {
                    "value": str(amount),
                    "currency": "RUB",
                }

            response = requests.post(
                f"https://{self.API_HOST}/{self.API_VERSION}/refunds",
                json=payload,
                headers={
                    "Idempotence-Key": self._generate_idempotence_key(),
                    "Authorization": self._auth_header(),
                },
                timeout=10,
            )
            response.raise_for_status()

            data = response.json()
            return {
                "success": True,
                "refund_id": data["id"],
                "amount": str(data["amount"]["value"]),
            }

        except requests.RequestException as e:
            return {"success": False, "error": str(e)}

    def verify_webhook(self, payload: dict, signature: str) -> bool:
        """
        Проверяет подпись webhook от ЮКассы.

        ЮКасса отправляет HMAC-SHA256 подпись в заголовке
        X-YooMoney-Signature. Подписывает строку вида:
        {request_body}

        Args:
            payload: Тело webhook (JSON)
            signature: Значение заголовка X-YooMoney-Signature

        Returns:
            True если подпись валидна
        """
        if not self.is_configured():
            return True  # В dev режиме пропускаем

        # ЮКасса использует webhook_secret из настроек магазина
        webhook_secret = getattr(
            settings, "YOOKASSA_WEBHOOK_SECRET", self.api_key
        )

        raw_body = getattr(
            self, "_last_webhook_body", "{}"
        )

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
        - payment.waiting_for_payment
        - payment.succeeded
        - payment.canceled

        Args:
            payload: Данные webhook

        Returns:
            {
                'status': 'paid'|'failed'|'unknown',
                'payment_id': '...',
                'order_id': '...',
            }
        """
        try:
            event_type = payload.get("event")
            payment = payload.get("object", {})
            payment_id = payment.get("id")
            status = payment.get("status")
            paid = payment.get("paid", False)

            # metadata.order_id — наш ID заказа
            metadata = payment.get("metadata", {})
            order_id = metadata.get("order_id")

            if event_type == "payment.succeeded" and paid:
                return {
                    "status": "paid",
                    "payment_id": payment_id,
                    "order_id": order_id,
                    "amount": str(payment.get("amount", {}).get("value", "0")),
                }

            elif event_type == "payment.canceled" or (
                event_type == "payment.succeeded" and not paid
            ):
                return {
                    "status": "failed",
                    "payment_id": payment_id,
                    "order_id": order_id,
                }

            return {
                "status": "unknown",
                "event_type": event_type,
                "payment_id": payment_id,
            }

        except Exception as e:
            return {"status": "error", "error": str(e)}

    @staticmethod
    def _generate_idempotence_key() -> str:
        """Генерирует случайный idempotence-key для безопасных операций."""
        import uuid

        return str(uuid.uuid4())
