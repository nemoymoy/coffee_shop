"""Payment service for YooKassa (ЮКасса) integration."""
from decimal import Decimal
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
        self, order_number: str, amount: Decimal, description: str
    ) -> dict:
        return self._yookassa.create_payment(
            order_number=order_number,
            amount=amount,
            description=description,
        )

    def handle_webhook(self, payload: str) -> dict:
        return self._yookassa.process_webhook(payload)


# Backward-compatible alias
yoomoney = YooMoneyService()
