"""Payment service for YooKassa (ЮКасса) integration."""
from decimal import Decimal
from django.utils import timezone
from .yookassa_service import YooKassaService


class YooMoneyService:
    """
    DEPRECATED: Use YooKassaService instead.
    This class is kept for backward compatibility.
    """

    def __init__(self):
        self._yookassa = YooKassaService()

    def is_configured(self) -> bool:
        return self._yookassa.is_configured()

    def create_payment_link(
        self, order_id: int, amount: Decimal, description: str
    ) -> dict:
        return self._yookassa.create_payment(
            order_id=order_id,
            amount=amount,
            description=description,
        )

    def handle_webhook(self, payload: dict) -> dict:
        return self._yookassa.process_webhook(payload)


# Backward-compatible alias
yoomoney = YooMoneyService()
