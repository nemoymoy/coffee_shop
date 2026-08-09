"""Promo code application service."""
from decimal import Decimal
from typing import Tuple, Optional

from ..models import PromoCode


class PromoService:
    """Сервис применения промокодов."""

    @staticmethod
    def validate_promo_code(code: str) -> Tuple[bool, Optional[PromoCode], str]:
        """
        Проверить промокод на валидность.

        Args:
            code: Строка промокода

        Returns:
            (is_valid, promo_code_instance, error_message)
            Если is_valid=True, promo_code_instance не None, error_message=''
        """
        code = code.strip()
        if not code:
            return False, None, 'Промокод не указан'

        try:
            promo = PromoCode.objects.get(code__iexact=code)
        except PromoCode.DoesNotExist:
            return False, None, 'Промокод не найден'

        if not promo.is_valid:
            if not promo.is_active:
                return False, None, 'Промокод деактивирован'
            from django.utils import timezone
            now = timezone.now()
            if now < promo.valid_from:
                return False, None, 'Промокод ещё не активен'
            if now > promo.valid_to:
                return False, None, 'Промокод истёк'
            if promo.max_uses > 0 and promo.used_count >= promo.max_uses:
                return False, None, 'Промокод исчерпан'

        return True, promo, ''

    @staticmethod
    def apply_discount(total: Decimal, promo: PromoCode) -> Decimal:
        """
        Применить скидку промокода к общей сумме.

        Args:
            total: Общая сумма заказа
            promo: Валидный объект PromoCode

        Returns:
            Итоговая сумма после применения скидки
        """
        if promo.discount_type == 'percent':
            discount_amount = total * promo.discount_value / Decimal('100')
            return max(Decimal('0'), total - discount_amount)
        else:  # fixed
            return max(Decimal('0'), total - promo.discount_value)

    @staticmethod
    def record_promo_usage(promo: PromoCode) -> None:
        """
        Зафиксировать использование промокода.

        Увеличивает used_count на 1.
        """
        promo.used_count += 1
        promo.save(update_fields=['used_count', 'updated_at'])

    @staticmethod
    def calculate_promo_info(promo: PromoCode) -> dict:
        """
        Получить информацию о промокоде для отображения в UI.

        Returns:
            Словарь с параметрами промокода
        """
        discount_display = ''
        if promo.discount_type == 'percent':
            discount_display = f'{promo.discount_value}%'
        else:
            discount_display = f'{promo.discount_value} ₽'

        return {
            'id': promo.id,
            'code': promo.code,
            'discount_type': promo.discount_type,
            'discount_value': str(promo.discount_value),
            'discount_display': discount_display,
            'remaining_uses': promo.remaining_uses,
            'is_valid': promo.is_valid,
        }
