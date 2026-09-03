"""Stock management service."""
from decimal import Decimal
from typing import List, Tuple
from django.db import transaction, models
from django.conf import settings
from django.utils import timezone


class StockService:
    """Сервис управления остатками товаров."""

    RESERVATION_TIMEOUT_MINUTES = getattr(
        settings, 'STOCK_RESERVATION_TIMEOUT_MINUTES', 30
    )

    @staticmethod
    def get_available_stock(product) -> int:
        """
        Получить доступный остаток товара (stock - зарезервировано).

        Args:
            product: Модель Product

        Returns:
            Доступное количество на складе
        """
        reserved = StockService.get_reserved_stock(product.pk)
        return max(0, product.stock - reserved)

    @staticmethod
    def get_reserved_stock(product_id: int) -> int:
        """
        Получить количество товара, зарезервированное в неоплаченных заказах.

        Args:
            product_id: ID товара

        Returns:
            Зарезервированное количество
        """
        from ..models import Order, OrderItem

        reserved_items = (
            OrderItem.objects
            .filter(
                order__status__in=['new', 'awaiting_payment', 'in_progress'],
                product_id=product_id,
            )
            .select_related('order')
        )

        reserved = 0
        for item in reserved_items:
            # Проверяем, что резерв ещё не списан (заказ не оплачен и не отменён)
            if item.order.status in ['new', 'awaiting_payment', 'in_progress']:
                if item.coffee_weight_grams:
                    reserved += item.coffee_weight_grams
                else:
                    reserved += item.quantity

        return reserved

    @staticmethod
    def is_available(product, weight: int = None, quantity: int = 1) -> Tuple[bool, str]:
        """
        Проверить доступность товара.

        Args:
            product: Модель Product
            weight: Вес товара (для кофе в граммах)
            quantity: Количество (для не-кофе)

        Returns:
            (is_available, error_message)
        """
        available = StockService.get_available_stock(product)
        required = weight if weight else quantity

        if required > available:
            return False, f'Доступно не более {available} шт'
        if available <= 0:
            return False, 'Товар закончился'

        return True, ''

    @staticmethod
    @transaction.atomic
    def reserve_stock(order_id: int) -> bool:
        """
        Резервировать остатки для заказа.

        Для заказа со статусом 'new' меняет статус на 'awaiting_payment'.
        Для заказа со статусом 'awaiting_payment' просто резервирует stock.

        Args:
            order_id: ID заказа

        Returns:
            True если резерв успешен
        """
        from ..models import Order

        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            return False

        # Проверяем доступность всех товаров в заказе
        for item in order.items.all():
            product = item.product
            if item.coffee_weight_grams:
                available = StockService.get_available_stock(product)
                if item.coffee_weight_grams > available:
                    return False
            else:
                available = StockService.get_available_stock(product)
                if item.quantity > available:
                    return False

        # Меняем статус на awaiting_payment только для заказов со статусом 'new'
        # (для online-оплаты статус уже awaiting_payment, для cash — остаётся new)
        if order.status == 'new':
            order.status = 'awaiting_payment'

        order.reserved_at = timezone.now()
        order.save(update_fields=['status', 'reserved_at', 'updated_at'])

        return True

    @staticmethod
    @transaction.atomic
    def confirm_stock(order_id: int) -> None:
        """
        Подтвердить резервирование — списать остатки.

        Вызывается при оплате заказа через webhook ЮКассы.

        Args:
            order_id: ID заказа
        """
        from ..models import Order

        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            return

        if order.status not in ('awaiting_payment', 'new'):
            return

        for item in order.items.all():
            product = item.product
            if item.coffee_weight_grams:
                product.stock -= item.coffee_weight_grams
            else:
                product.stock -= item.quantity
            product.save(update_fields=['stock'])

        order.reserved_at = None
        order.save(update_fields=['reserved_at', 'updated_at'])

    @staticmethod
    @transaction.atomic
    def release_stock(order_id: int) -> None:
        """
        Освободить резервирование — вернуть остатки.

        Вызывается при отмене заказа или истечении таймаута.

        Args:
            order_id: ID заказа
        """
        from ..models import Order

        try:
            order = Order.objects.select_for_update().get(pk=order_id)
        except Order.DoesNotExist:
            return

        if order.status not in ('awaiting_payment', 'new'):
            return

        for item in order.items.all():
            product = item.product
            if item.coffee_weight_grams:
                product.stock += item.coffee_weight_grams
            else:
                product.stock += item.quantity
            product.save(update_fields=['stock'])

        order.status = 'cancelled'
        order.reserved_at = None
        order.save(update_fields=['status', 'reserved_at', 'updated_at'])

    @staticmethod
    def release_expired_reservations() -> int:
        """
        Освободить истёкшие резервы.

        Запускается периодически через Celery Beat.

        Returns:
            Количество освобождённых заказов
        """
        from ..models import Order

        threshold = timezone.now() - timezone.timedelta(
            minutes=StockService.RESERVATION_TIMEOUT_MINUTES
        )

        expired = Order.objects.filter(
            status='awaiting_payment',
            reserved_at__lt=threshold,
        )

        released = 0
        for order in expired:
            StockService.release_stock(order.pk)
            released += 1

        return released

    @staticmethod
    def recalculate_total(order) -> Decimal:
        """
        Пересчитать сумму заказа на основе актуальных остатков.

        Args:
            order: Модель Order

        Returns:
            Новая сумма заказа
        """
        total = Decimal('0.00')
        for item in order.items.all():
            total += item.total_price
        order.total_amount = total
        order.save(update_fields=['total_amount', 'updated_at'])
        return total
