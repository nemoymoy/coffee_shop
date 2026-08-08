"""Cart service."""
from typing import Optional
from django.db import transaction
from decimal import Decimal
from coffee_shop.apps.catalog.models import Product


class CartService:
    """Сервис корзины."""

    @staticmethod
    def _calc_price(weight: int, price_per_50g: Decimal) -> Decimal:
        """Внутренний расчёт цены кофе."""
        if weight <= 0:
            return Decimal('0.00')
        units = weight // 50
        return units * price_per_50g

    @staticmethod
    def get_cart_item_data(
        product,
        weight: int,
        coffee_form: str,
        brewing_method: Optional[str] = None
    ) -> dict:
        """
        Подготавливает данные для корзины.
        """
        if product.product_type == 'coffee':
            price = CartService._calc_price(weight, product.price_per_50g)
        else:
            price = product.base_price or Decimal('0.00')

        return {
            'product': product,
            'quantity': 1,
            'unit_price': price,
            'coffee_weight_grams': weight if product.product_type == 'coffee' else None,
            'coffee_form': coffee_form if product.product_type == 'coffee' else None,
            'brewing_method': brewing_method if product.product_type == 'coffee' else None,
        }

    @staticmethod
    @transaction.atomic
    def create_order_item(
        order,
        product,
        weight: int,
        coffee_form: str,
        brewing_method: Optional[str] = None
    ):
        """
        Создаёт OrderItem с проверкой остатков.
        """
        if product.product_type == 'coffee':
            if weight > product.stock:
                raise ValueError(f'На складе только {product.stock} г')
            product.stock -= weight
            product.save(update_fields=['stock'])
            price = CartService._calc_price(weight, product.price_per_50g)
        else:
            if product.stock < 1:
                raise ValueError('Товар закончился')
            product.stock -= 1
            product.save(update_fields=['stock'])
            price = product.base_price or Decimal('0.00')

        return order.items.create(
            product=product,
            quantity=1,
            unit_price=price,
            coffee_weight_grams=weight if product.product_type == 'coffee' else None,
            coffee_form=coffee_form if product.product_type == 'coffee' else None,
            brewing_method=brewing_method if product.product_type == 'coffee' else None,
        )
