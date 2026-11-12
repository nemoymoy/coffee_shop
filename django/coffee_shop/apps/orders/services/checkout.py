"""Checkout service — Order creation and processing.

Extracted from order_views.py::checkout_view to eliminate the
God Function and improve testability.
"""
import logging

from decimal import Decimal

from django.db import transaction
from django.contrib import messages

from coffee_shop.apps.orders.forms.order_form import OrderForm
from coffee_shop.apps.orders.models import Order, OrderItem, Package
from coffee_shop.apps.orders.services.delivery_creator import DeliveryCreator
from coffee_shop.apps.orders.services.promo_service import PromoService
from coffee_shop.apps.orders.services.stock_service import StockService
from coffee_shop.tasks import (
    send_order_confirmation_email,
    send_order_status_changed_email,
    send_order_to_store_email,
)

logger = logging.getLogger(__name__)


class CheckoutValidator:
    """Validate checkout form data, phone, promo code, delivery."""

    @staticmethod
    def validate(form, request):
        """Validate the order form and return enriched cleaned data.

        Returns:
            dict with keys:
                order_data (dict) — fields for Order.objects.create
                promo (PromoCode or None)
                delivery_info (dict) — delivery cost, type, claim_id, etc.
                needs_delivery (bool)
        """
        cleaned = form.cleaned_data
        cart = request.session.get('cart', {})

        # ── Phone normalization ──────────────────────────────────────
        phone = cleaned.get('phone', '')
        if phone:
            digits = ''.join(c for c in phone if c.isdigit())
            if digits.startswith('8') and len(digits) == 11:
                digits = '7' + digits[1:]
            elif not digits.startswith('7') and len(digits) == 10:
                digits = '7' + digits
            phone = '+' + digits
            cleaned['phone'] = phone

        # ── Promo code validation ────────────────────────────────────
        promo_code_str = cleaned.get('promo_code', '')
        promo = None
        if promo_code_str:
            is_valid, promo, error = PromoService.validate_promo_code(promo_code_str)
            if not is_valid:
                messages.error(request, error)
                return None

        # ── Delivery type / API type ─────────────────────────────────
        delivery_type_raw = (
            cleaned.get('delivery_type', '') or request.POST.get('delivery_type', '')
        )
        if delivery_type_raw not in dict(Order.DeliveryType.choices):
            if cleaned['delivery_method'] == 'pickup':
                delivery_type_raw = ''
            else:
                delivery_type_raw = 'courier'

        # Determine API type
        if delivery_type_raw in ('pickup', 'postamat'):
            delivery_api_type = 'other_day'
        else:
            delivery_api_type = 'express'

        # ── Initial status ───────────────────────────────────────────
        payment_method = cleaned['payment_method']
        initial_status = (
            Order.Status.AWAITING_PAYMENT if payment_method == 'online'
            else Order.Status.NEW
        )

        # ── Delivery validation ──────────────────────────────────────
        needs_delivery = (
            cleaned['delivery_method'] == Order.DeliveryMethod.DELIVERY
        )
        if needs_delivery and not cleaned.get('delivery_address', ''):
            messages.error(request, 'Необходимо указать адрес доставки')
            return None

        order_data = {
            'user': request.user if request.user.is_authenticated else None,
            'first_name': cleaned['first_name'],
            'last_name': cleaned['last_name'],
            'phone': cleaned['phone'],
            'email': cleaned['email'],
            'comment': cleaned.get('comment', ''),
            'delivery_method': cleaned['delivery_method'],
            'delivery_type': delivery_type_raw,
            'delivery_api_type': delivery_api_type,
            'payment_method': payment_method,
            'delivery_address': cleaned.get('delivery_address', ''),
            'pvz_id': cleaned.get('pvz_id', '') or request.POST.get('pvz_id', '') or None,
            'destination_coords': (
                cleaned.get('destination_coords', '')
                or request.POST.get('destination_coords', '')
            ) or None,
            'client_order_id': None,
            'delivery_interval_from': cleaned.get('delivery_interval_from', None),
            'delivery_interval_to': cleaned.get('delivery_interval_to', None),
            'recipient_name': f"{cleaned['last_name']} {cleaned['first_name']}",
            'recipient_phone': cleaned['phone'],
            'express_claim_id': (
                request.POST.get('express_claim_id', '') or None
            ),
            'status': initial_status,
        }

        delivery_info = {
            'delivery_cost': cleaned.get('delivery_cost')
                             or request.POST.get('delivery_cost', '0'),
            'express_claim_id': request.POST.get('express_claim_id', ''),
            'delivery_date': cleaned.get('delivery_date', '')
                             or request.POST.get('delivery_date', ''),
            'yandex_request_id': cleaned.get('yandex_request_id', '')
                                 or request.POST.get('yandex_request_id', ''),
        }

        return {
            'order_data': order_data,
            'promo': promo,
            'delivery_info': delivery_info,
            'needs_delivery': needs_delivery,
        }


class OrderFactory:
    """Create Order + OrderItems inside a transaction."""

    @staticmethod
    def create(order_data, cart, applied_promo, request=None):
        """Create an Order with OrderItems.

        Args:
            order_data: dict of Order fields.
            cart: session cart dict.
            applied_promo: PromoCode instance or None.
            request: Optional HttpRequest for messages.

        Returns:
            Created Order instance.
        """
        with transaction.atomic():
            # Ensure total_amount has a default so Order can be created
            order_data.setdefault('total_amount', Decimal('0'))
            order = Order.objects.create(**order_data)
            # Set client_order_id after save
            order.client_order_id = str(order.pk)
            order.save(update_fields=['client_order_id'])

            total = Decimal('0')
            for key, value in cart.items():
                try:
                    from coffee_shop.apps.catalog.models import Product
                    product = Product.objects.get(pk=value['product_id'])
                    unit_price = value['price']

                    # Validation via available stock
                    if product.stock_unit == Product.STOCK_UNIT_GRAM:
                        weight = int(value['weight'])
                        if weight > product.available_stock:
                            raise ValueError(
                                f'На складе только {product.available_stock} '
                                f'{product.stock_unit_label}'
                            )
                    else:
                        if product.available_stock < 1:
                            raise ValueError('Товар закончился')

                    # Determine weight
                    if product.stock_unit == Product.STOCK_UNIT_GRAM:
                        weight_grams = int(value.get('weight', 0)) if value.get('weight') else 0
                    else:
                        weight_grams = product.weight_grams

                    package = None
                    if weight_grams > 0:
                        try:
                            package = Package.for_weight(weight_grams)
                        except Package.DoesNotExist:
                            package = None

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=1,
                        unit_price=unit_price,
                        coffee_weight_grams=(
                            value.get('weight')
                            if product.stock_unit == Product.STOCK_UNIT_GRAM
                            else None
                        ),
                        coffee_form=(
                            value.get('coffee_form')
                            if product.stock_unit == Product.STOCK_UNIT_GRAM
                            else None
                        ),
                        brewing_method=(
                            value.get('brewing_method')
                            if product.stock_unit == Product.STOCK_UNIT_GRAM
                            else None
                        ),
                        package=package,
                        weight_grams=weight_grams,
                    )
                    total += Decimal(str(unit_price))
                except (Product.DoesNotExist, ValueError) as e:
                    if request is not None:
                        messages.warning(request, str(e))
                    continue

            # Apply promo discount
            if applied_promo:
                total = PromoService.apply_discount(total, applied_promo)
                PromoService.record_promo_usage(applied_promo)

            order.total_amount = total
            order.save()

        return order


class CheckoutExecutor:
    """Coordinate the checkout flow: validate → create → delivery → stock → email."""

    def execute(self, request, form):
        """Execute the full checkout flow.

        Args:
            request: Django HttpRequest.
            form: Validated OrderForm.

        Returns:
            (order, messages) tuple.
        """
        validated = CheckoutValidator.validate(form, request)
        if validated is None:
            return None, []

        order_data = validated['order_data']
        applied_promo = validated['promo']
        delivery_info = validated['delivery_info']
        needs_delivery = validated['needs_delivery']
        cart = request.session.get('cart', {})

        # ── Create order ─────────────────────────────────────────────
        order = OrderFactory.create(order_data, cart, applied_promo, request)

        # ── Delivery ─────────────────────────────────────────────────
        delivery_price = self._process_delivery(
            request, order, needs_delivery, delivery_info, cart
        )

        # ── Update totals ────────────────────────────────────────────
        order.delivery_cost = delivery_price
        order.total_amount = Decimal(str(order.total_amount)) + delivery_price

        fields_to_save = ['delivery_cost', 'total_amount']
        if order.yandex_order_id:
            fields_to_save.extend(['yandex_order_id', 'tracking_number',
                                   'yandex_delivery_status', 'status'])
        if order.express_claim_id:
            fields_to_save.append('express_claim_id')
        if order.yandex_offer_id:
            fields_to_save.append('yandex_offer_id')
        if order.yandex_delivery_status:
            fields_to_save.append('yandex_delivery_status')
        order.save(update_fields=fields_to_save)

        # ── Stock reservation ────────────────────────────────────────
        if (
            not needs_delivery
            and order.payment_method == Order.PaymentMethod.ONLINE
        ):
            StockService.reserve_stock(order.pk)

        # ── Clear cart ───────────────────────────────────────────────
        if 'cart' in request.session:
            del request.session['cart']

        # ── Emails ───────────────────────────────────────────────────
        goods_total = sum(
            (item.total_price for item in order.items.all()),
            Decimal('0'),
        )
        send_order_confirmation_email.delay(order.pk)
        send_order_to_store_email.delay(order.pk, goods_total)

        return order, []

    def _process_delivery(self, request, order, needs_delivery,
                          delivery_info, cart):
        """Process Yandex Delivery creation for the order.

        Returns:
            Decimal delivery cost.
        """
        delivery_cost_str = delivery_info.get('delivery_cost', '0')
        delivery_price = Decimal(str(delivery_cost_str)) if delivery_cost_str else Decimal('0')

        if not needs_delivery:
            return delivery_price

        payment_method = order.payment_method

        # For cash payment with Express API — create delivery now
        # For online payment — delivery is created in payment_webhook
        # For Other Day API — delivery is created in payment_webhook
        if (
            payment_method != Order.PaymentMethod.ONLINE
            and order.delivery_api_type == 'express'
        ):
            try:
                coords = self._parse_coords(order.destination_coords)
                address = order.delivery_address
                existing_claim_id = delivery_info.get('express_claim_id', '')

                creator = DeliveryCreator(order)
                result = creator.create(
                    address=address,
                    coords=coords,
                    delivery_cost=delivery_price,
                    existing_claim_id=existing_claim_id or None,
                )

                if result.get('success'):
                    if order.delivery_api_type == 'express':
                        if not order.express_claim_id:
                            order.express_claim_id = result.get('claim_id', '')
                        order.yandex_order_id = order.express_claim_id
                        yandex_status = result.get('status', 'accepted').lower()
                        order.yandex_delivery_status = yandex_status
                        order.yandex_delivery_status_raw = result.get('status', 'accepted')
                        order.status = 'in_progress'
                        messages.info(request, 'Заказ на доставку создан в Яндекс Доставке')
                else:
                    messages.warning(
                        request,
                        f'Не удалось создать заказ в Яндекс Доставке: '
                        f'{result.get("error", "unknown")}',
                    )
            except Exception as e:
                logger.exception(
                    '[Checkout] Failed to create Yandex delivery for order %s',
                    order.pk,
                )
                messages.warning(request, f'Не удалось создать заказ в Яндекс Доставке: {e}')

        return delivery_price

    @staticmethod
    def _parse_coords(coords_str):
        """Parse destination_coords string to [lon, lat] list."""
        if not coords_str:
            return [49.35, 53.21]
        try:
            return [float(c.strip()) for c in coords_str.split(',')]
        except (ValueError, TypeError):
            return [49.35, 53.21]
