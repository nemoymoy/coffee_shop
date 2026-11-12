"""Orders views."""
import json
import logging
from decimal import Decimal

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET
from django.views.decorators.cache import never_cache
from django.contrib.auth.decorators import login_required
from rest_framework.decorators import permission_classes
from rest_framework.permissions import IsAdminUser

from coffee_shop.apps.catalog.models import Product
from coffee_shop.apps.catalog.services import coffee_price
from coffee_shop.apps.orders.services.stock_service import StockService
from coffee_shop.apps.orders.services.promo_service import PromoService
from coffee_shop.apps.orders.services.delivery_creator import DeliveryCreator
from coffee_shop.apps.orders.services.checkout import CheckoutExecutor
from coffee_shop.apps.users.models import UserProfile

from coffee_shop.apps.orders.forms.order_form import OrderForm
from coffee_shop.apps.orders.models import Order, OrderItem
from coffee_shop.tasks import (
    send_order_confirmation_email,
    send_order_status_changed_email,
    send_order_to_store_email,
)

logger = logging.getLogger(__name__)


# ── Cart Views ──────────────────────────────────────────────────────


def cart_view(request):
    """Отображение корзины."""
    cart_data = request.session.get('cart', {})
    cart_with_products = {}
    total = 0

    brewing_labels = dict(Product.BREWING_CHOICES)

    for key, value in cart_data.items():
        try:
            product = Product.objects.get(pk=value['product_id'])
            price = value.get('price', 0)
            total += price
            item = dict(value)
            if product.stock_unit == Product.STOCK_UNIT_GRAM:
                item['coffee_weight_grams'] = item.get('weight', 50)
            else:
                item['coffee_weight_grams'] = None
            if 'coffee_form' not in item:
                item['coffee_form'] = value.get('coffee_form', 'beans')
            brewing_method = value.get('brewing_method', '')
            item['brewing_method'] = brewing_method
            if brewing_method and brewing_method in brewing_labels:
                item['brewing_method_label'] = brewing_labels[brewing_method]
            else:
                item['brewing_method_label'] = ''
            item['product_weight_grams'] = value.get('product_weight_grams', 0)
            item['product'] = product
            item['price'] = price
            cart_with_products[key] = item
        except Product.DoesNotExist:
            pass

    for key, item in cart_with_products.items():
        if item.get('product'):
            product = item['product']
            available = StockService.get_available_stock(product)
            item['max_quantity'] = available + int(item.get('quantity', 1))

    context = {
        'cart': cart_with_products,
        'cart_items': list(cart_with_products.values()),
        'total': total,
    }
    return render(request, 'cart.html', context)


def cart_remove(request):
    """Удаление товара из корзины (AJAX)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)

    if not request.user.is_authenticated:
        return JsonResponse({
            'error': 'login_required',
            'redirect': '/accounts/login/'
        }, status=403)

    key = request.POST.get('key')
    if not key:
        return JsonResponse({'error': 'Key is required'}, status=400)

    cart = request.session.get('cart', {})
    if key in cart:
        del cart[key]
        request.session['cart'] = cart

    return JsonResponse({
        'success': True,
        'cart_count': len(cart),
    })


def cart_update(request):
    """Обновление количества товара в корзине (AJAX)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)

    if not request.user.is_authenticated:
        return JsonResponse({
            'error': 'login_required',
            'redirect': '/accounts/login/'
        }, status=403)

    key = request.POST.get('key')
    new_quantity_str = request.POST.get('quantity', '')

    if not key:
        return JsonResponse({'error': 'Key is required'}, status=400)

    try:
        new_quantity = int(new_quantity_str)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Некорр��ктное количество'}, status=400)

    if new_quantity < 1:
        return JsonResponse({'error': 'Минимальное количество — 1'}, status=400)

    cart = request.session.get('cart', {})
    if key not in cart:
        return JsonResponse({'error': 'Товар не найден в корзине'}, status=404)

    item = cart[key]
    try:
        product = Product.objects.get(pk=item['product_id'])
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Товар не найден'}, status=404)

    current_qty = int(item.get('quantity', 1))
    available = StockService.get_available_stock(product) + current_qty

    if product.stock_unit == Product.STOCK_UNIT_GRAM:
        if new_quantity % 50 != 0:
            return JsonResponse({'error': 'Вес должен быть кратен 50 г'}, status=400)
        if new_quantity < 50:
            return JsonResponse({'error': 'Минимальный вес — 50 г'}, status=400)
        if new_quantity > available:
            return JsonResponse({'error': f'Доступно не более {available} г'}, status=400)

        price = coffee_price(new_quantity, product.price_per_50g)
        item_data = dict(cart[key])
        item_data['weight'] = str(new_quantity)
        item_data['quantity'] = new_quantity
        item_data['price'] = float(price)
        new_key = f"{product.id}:{new_quantity}:{item.get('coffee_form', 'beans')}:{item.get('brewing_method', '')}"
        if new_key != key:
            del cart[key]
            cart[new_key] = item_data
            key = new_key
        else:
            cart[key] = item_data
    else:
        if new_quantity < 1:
            return JsonResponse({'error': 'Минимальное количество — 1'}, status=400)
        if new_quantity > available:
            return JsonResponse({'error': f'Доступно не более {available} шт'}, status=400)

        cart[key]['quantity'] = new_quantity
        cart[key]['price'] = float(product.base_price) * new_quantity

    request.session['cart'] = cart

    return JsonResponse({
        'success': True,
        'cart_count': len(cart),
        'new_price': cart[key]['price'],
        'new_key': key,
    })


def cart_add(request):
    """Добавление товара в корзину (AJAX)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)

    logger.info('[cart_add] User authenticated: %s, CSRF valid: %s',
                request.user.is_authenticated,
                hasattr(request, 'csrf_token'))

    if not request.user.is_authenticated:
        logger.warning('[cart_add] User not authenticated, returning 403')
        return JsonResponse({
            'error': 'login_required',
            'redirect': '/accounts/login/'
        }, status=403)

    try:
        if not request.user.profile.is_email_verified:
            return JsonResponse({
                'error': 'email_not_verified',
                'message': 'Для добавления товаров в корзину необходимо подтвердить email',
                'redirect': '/accounts/verification-pending/',
            }, status=403)
    except UserProfile.DoesNotExist:
        return JsonResponse({
            'error': 'email_not_verified',
            'message': 'Для добавления товаров в корзину необходимо подтвердить email',
            'redirect': '/accounts/verification-pending/',
        }, status=403)

    product_id = request.POST.get('product_id')
    weight = request.POST.get('weight')
    coffee_form = request.POST.get('coffee_form')
    brewing_method = request.POST.get('brewing_method')

    if not product_id:
        return JsonResponse({'error': 'Product ID is required'}, status=400)

    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)
    except (ValueError, TypeError):
        return JsonResponse({'error': 'Invalid product ID'}, status=400)

    from coffee_shop.apps.catalog.services import CoffeeService

    if product.stock_unit == Product.STOCK_UNIT_GRAM:
        if not weight:
            return JsonResponse({'error': 'Weight is required for coffee'}, status=400)
        try:
            weight_int = int(weight)
        except (ValueError, TypeError):
            return JsonResponse({'error': 'Invalid weight value'}, status=400)
        is_valid, error = CoffeeService.validate_all(
            product, weight_int, coffee_form, brewing_method
        )
        if not is_valid:
            return JsonResponse({'error': error}, status=400)

        price = coffee_price(weight_int, product.price_per_50g)
    else:
        price = product.base_price

    cart = request.session.get('cart', {})
    if product.stock_unit == Product.STOCK_UNIT_GRAM:
        cart_key = f"{product_id}:{weight}:{coffee_form}:{brewing_method or ''}"
    else:
        cart_key = f"{product_id}:noncoffee"
    cart[cart_key] = {
        'product_id': product_id,
        'weight': weight,
        'coffee_form': coffee_form,
        'brewing_method': brewing_method,
        'price': float(price),
        'quantity': int(weight) if product.stock_unit == Product.STOCK_UNIT_GRAM else 1,
        'product_weight_grams': (
            product.weight_grams if product.stock_unit == Product.STOCK_UNIT_UNIT else 0
        ),
    }
    request.session['cart'] = cart

    return JsonResponse({
        'success': True,
        'cart_count': len(cart),
    })


# ── Checkout ────────────────────────────────────────────────────────


def checkout_view(request):
    """Оформление заказа."""
    cart = request.session.get('cart', {})
    if not cart:
        messages.error(request, 'Корзина пуста')
        return redirect('catalog:catalog')

    if request.method == 'POST':
        form = OrderForm(request.POST)
        if not form.is_valid():
            # Rebuild cart_items for error display
            cart_items, total = _build_cart_items(cart)
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
            return render(request, 'checkout.html', {
                'cart_items': cart_items,
                'form': form,
                'total': total,
            })

        executor = CheckoutExecutor()
        order, _ = executor.execute(request, form)
        if order is None:
            # Validation failed, messages already set
            cart_items, total = _build_cart_items(cart)
            return render(request, 'checkout.html', {
                'cart_items': cart_items,
                'form': OrderForm(request.POST),
                'total': total,
            })

        return redirect('orders:order_success', order_id=order.pk)

    # GET — render checkout form
    user_data = {}
    if request.user.is_authenticated:
        user_data = {
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'email': request.user.email,
        }
        try:
            phone = request.user.profile.phone
            if phone:
                user_data['phone'] = phone
        except UserProfile.DoesNotExist:
            pass

    cart_items, total = _build_cart_items(cart)

    from django.urls import reverse

    context = {
        'cart_items': cart_items,
        'form': OrderForm(initial=user_data),
        'user_data': user_data,
        'total': total,
        'YANDEX_DELIVERY_WEBHOOK_URL': reverse('orders:yandex_webhook'),
        'YANDEX_SHOP_LAT': getattr(settings, 'YANDEX_SHOP_LAT', 53.1960),
        'YANDEX_SHOP_LON': getattr(settings, 'YANDEX_SHOP_LON', 49.3782),
        'YANDEX_SHOP_ADDRESS': getattr(settings, 'YANDEX_SHOP_ADDRESS', 'Самара, ул. Революционная, д. 3'),
        'YANDEX_PVZ_ID': getattr(settings, 'YANDEX_PVZ_ID', 'd0222b1e-73ff-4274-9c68-42c79d4c7eae'),
        'YANDEX_PVZ_LAT': getattr(settings, 'YANDEX_PVZ_LAT', 53.200850),
        'YANDEX_PVZ_LON': getattr(settings, 'YANDEX_PVZ_LON', 50.150500),
        'YANDEX_PVZ_ADDRESS': getattr(settings, 'YANDEX_PVZ_ADDRESS', 'г. Самара, ул. Лукачева, д. 6'),
    }
    return render(request, 'checkout.html', context)


# ── Promo ───────────────────────────────────────────────────────────


def promo_check(request):
    """Проверка промокода (AJAX)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)

    code = request.POST.get('code', '').strip()
    if not code:
        return JsonResponse({'error': 'Промокод не указан'}, status=400)

    is_valid, promo, error = PromoService.validate_promo_code(code)
    if not is_valid:
        return JsonResponse({'error': error}, status=400)

    info = PromoService.calculate_promo_info(promo)
    return JsonResponse({'success': True, 'promo': info})


# ── Order Pages ─────────────────────────────────────────────────────


def order_success(request, order_id):
    """Страница успешного заказа."""
    order = get_object_or_404(Order, pk=order_id)
    goods_total = sum(
        (item.total_price for item in order.items.all()),
        Decimal('0'),
    )
    return render(request, 'order_success.html', {
        'order': order,
        'goods_total': goods_total,
    })


@login_required
def order_detail(request, pk):
    """Детальная страница заказа."""
    order = get_object_or_404(Order, pk=pk, user=request.user)
    goods_total = order.total_amount - order.delivery_cost
    return render(request, 'order_detail.html', {
        'order': order,
        'goods_total': float(goods_total),
    })


# ── Payment ─────────────────────────────────────────────────────────


def pay_order(request, order_id):
    """Перенаправление на страницу оплаты ЮКасса."""
    from coffee_shop.apps.orders.services.yookassa_service import YooKassaService
    from django.urls import reverse

    order = get_object_or_404(Order, pk=order_id)

    if order.status != Order.Status.AWAITING_PAYMENT:
        messages.error(request, 'Этот заказ не требует оплаты')
        return redirect('orders:order_success', order_id=order.pk)

    if order.payment_method != Order.PaymentMethod.ONLINE:
        messages.error(request, 'Для этого заказа не требуется онлайн-оплата')
        return redirect('orders:order_success', order_id=order.pk)

    yookassa = YooKassaService()
    if not yookassa.is_configured():
        error_msg = yookassa.get_config_error()
        messages.error(request, error_msg or 'ЮКасса не настроена')
        return redirect('orders:order_success', order_id=order.pk)

    return_url = request.build_absolute_uri(
        reverse('orders:payment_result') + f'?order_number={order.order_number}'
    )

    result = yookassa.create_payment(
        order_number=order.order_number,
        amount=order.total_amount,
        description=f'Заказ #{order.order_number} — {order.full_name}',
        confirm_type='redirect',
        return_url=return_url,
    )

    if result.get('success'):
        order.payment_id = result.get('payment_id')
        order.save(update_fields=['payment_id'])
        return redirect(result['confirmation_url'])
    else:
        messages.error(request, f'Ошибка создания платежа: {result.get("error", "неизвестная ошибка")}')
        return redirect('orders:order_success', order_id=order.pk)


@csrf_exempt
@require_POST
def payment_webhook(request):
    """Webhook endpoint for YooKassa payment notifications."""
    from .services.yookassa_service import YooKassaService

    client_ip = request.META.get('HTTP_X_FORWARDED_FOR', request.META.get('REMOTE_ADDR', 'unknown'))
    if client_ip and ',' in client_ip:
        client_ip = client_ip.split(',')[0].strip()

    try:
        body = request.body.decode('utf-8')
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.warning('Invalid JSON in webhook from IP: %s', client_ip)
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    yookassa = YooKassaService()

    signature = request.META.get('HTTP_X_YOOMONEY_SIGNATURE', '')
    if not yookassa.verify_webhook(body, signature):
        logger.warning('Webhook signature verification failed from IP: %s', client_ip)
        return HttpResponse("Forbidden", status=403)

    # Replay protection
    event_id = data.get('event_id', '')
    if event_id:
        from django.core.cache import cache
        cache_key = f'yookassa_event_{event_id}'
        if cache.get(cache_key):
            logger.info('Duplicate webhook event_id: %s from IP: %s', event_id, client_ip)
            return JsonResponse({"status": "ok"}, status=200)
        cache.set(cache_key, True, timeout=86400)

    result = yookassa.process_webhook(data)
    logger.info('Webhook processed: %s', result)

    if result.get('status') == 'paid':
        order_number = result.get('order_number')
        payment_id = result.get('payment_id')
        logger.info(
            'payment_webhook: Payment succeeded: order=%s, payment=%s',
            order_number, payment_id,
        )

        if order_number:
            try:
                order = Order.objects.select_for_update().get(order_number=order_number)

                webhook_amount = Decimal(str(result.get('amount', '0')))
                if webhook_amount != order.total_amount:
                    return HttpResponse("Amount mismatch", status=400)

                with transaction.atomic():
                    order.payment_id = payment_id

                    # Create/accept Yandex delivery for online payment
                    _create_delivery_for_paid_order(order)

                    order.status = Order.Status.PAID
                    save_fields = [
                        'payment_id', 'status', 'updated_at',
                        'yandex_order_id', 'tracking_number',
                        'yandex_delivery_status', 'yandex_delivery_status_raw',
                        'delivery_cost', 'total_amount',
                    ]
                    if order.express_claim_id:
                        save_fields.append('express_claim_id')
                    if order.yandex_offer_id:
                        save_fields.append('yandex_offer_id')
                    if order.delivery_interval_from or order.delivery_interval_to:
                        save_fields.extend(['delivery_interval_from', 'delivery_interval_to'])
                    order.save(update_fields=save_fields)
                    logger.info('Order status updated to PAID: %s', order.pk)

                    send_order_status_changed_email.delay(order.pk, 'in_progress')

            except (Order.DoesNotExist, ValueError) as e:
                logger.error('Error processing webhook: %s', e)

    return JsonResponse({"status": "ok"})


@csrf_exempt
@require_POST
@login_required
def create_payment_api(request):
    """API endpoint for creating a YooKassa payment."""
    from .services.yookassa_service import YooKassaService

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    order_number = data.get('order_number')
    amount_value = data.get('amount')

    if not order_number or not amount_value:
        return JsonResponse(
            {'error': 'order_number and amount are required'}, status=400
        )

    try:
        amount = Decimal(str(amount_value))
    except Exception:
        return JsonResponse({'error': 'Invalid amount'}, status=400)

    try:
        order = Order.objects.get(order_number=order_number)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)

    yookassa = YooKassaService()
    if not yookassa.is_configured():
        return JsonResponse({'error': 'Payment system not configured'}, status=500)

    return_url = f"{getattr(settings, 'SITE_URL', '')}/orders/payment/result/?order_number={order_number}"

    result = yookassa.create_payment(
        order_number=order.order_number,
        amount=order.total_amount,
        description=f"Payment for order #{order.order_number}",
        confirm_type='redirect',
        return_url=return_url,
    )

    if result.get('success'):
        order.payment_id = result.get('payment_id')
        order.save(update_fields=['payment_id'])
        return JsonResponse({
            'payment_id': result.get('payment_id'),
            'confirmation_url': result.get('confirmation_url'),
        })
    else:
        return JsonResponse(
            {'error': result.get('error', 'Unknown error')}, status=500
        )


@require_GET
def check_payment_status(request, payment_id):
    """Check payment status directly via API."""
    from .services.yookassa_service import YooKassaService

    yookassa = YooKassaService()
    result = yookassa.get_payment_status(payment_id)

    if result.get('success'):
        return JsonResponse({
            'status': result.get('status'),
            'paid': result.get('paid', False),
            'amount': result.get('amount'),
            'metadata': result.get('metadata', {}),
        })
    else:
        return JsonResponse(
            {'error': result.get('error', 'Unknown error')}, status=500
        )


@csrf_exempt
@require_POST
@login_required
@permission_classes([IsAdminUser])
def create_refund(request):
    """Full or partial refund for a successful payment."""
    from .services.yookassa_service import YooKassaService

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    payment_id = data.get('payment_id')
    amount_value = data.get('amount')

    if not payment_id:
        return JsonResponse({'error': 'payment_id is required'}, status=400)

    try:
        order = Order.objects.get(payment_id=payment_id)
    except Order.DoesNotExist:
        return JsonResponse({'error': 'Order not found'}, status=404)

    yookassa = YooKassaService()
    result = yookassa.refund_payment(
        payment_id=payment_id,
        amount=Decimal(str(amount_value)) if amount_value else None,
    )

    if result.get('success'):
        order.status = Order.Status.REFUNDED
        order.save(update_fields=['status'])
        return JsonResponse({
            'refund_id': result.get('refund_id'),
            'amount': result.get('amount'),
        })
    else:
        return JsonResponse(
            {'error': result.get('error', 'Unknown error')}, status=500
        )


@require_GET
def payment_result(request):
    """Страница результата оплаты — перенаправление от ЮКассы."""
    from .services.yookassa_service import YooKassaService
    from .services.stock_service import StockService

    order_number = request.GET.get('order_number')

    if order_number:
        try:
            order = Order.objects.get(order_number=order_number)

            if order.payment_id:
                yookassa = YooKassaService()
                payment_status = yookassa.get_payment_status(order.payment_id)

                if payment_status.get('success') and payment_status.get('paid'):
                    if order.status != Order.Status.PAID:
                        with transaction.atomic():
                            order.status = Order.Status.PAID
                            order.save(update_fields=['status', 'updated_at'])

                            # Create Yandex delivery for online payment
                            _create_delivery_for_paid_order(order)

                            # Save order after delivery creation updates yandex fields
                            save_fields = ['status', 'updated_at']
                            if order.yandex_order_id:
                                save_fields.extend(['yandex_order_id', 'tracking_number',
                                                    'yandex_delivery_status', 'yandex_delivery_status_raw'])
                            if order.express_claim_id:
                                save_fields.append('express_claim_id')
                            if order.yandex_offer_id:
                                save_fields.append('yandex_offer_id')
                            if order.delivery_interval_from or order.delivery_interval_to:
                                save_fields.extend(['delivery_interval_from', 'delivery_interval_to'])
                            order.save(update_fields=save_fields)

                            StockService.reserve_stock(order.pk)
                            send_order_status_changed_email.delay(order.pk, 'in_progress')

                    messages.success(request, 'Оплата прошла успешно!')
                elif payment_status.get('status') == 'pending':
                    messages.warning(request, 'Оплата обрабатывается. Статус обновится автоматически.')
                else:
                    messages.error(request, 'Оплата не прошла. Попробуйте снова.')
                    return redirect('orders:pay_order', order_id=order.pk)

            goods_total = sum(
                (item.total_price for item in order.items.all()),
                Decimal('0'),
            )
            return render(request, 'order_success.html', {
                'order': order,
                'goods_total': goods_total,
                'payment_processed': True,
            })
        except Order.DoesNotExist:
            messages.error(request, 'Заказ не найден')
            return redirect('orders:order_success', order_id=1)

    messages.warning(request, 'Нет данных об оплате')
    return redirect('catalog:catalog')


@permission_classes([IsAdminUser])
@never_cache
def checkout_config_view(request):
    """Return Yandex API keys for checkout frontend."""
    return JsonResponse({
        'YANDEX_GEOCODER_API_KEY': getattr(settings, 'YANDEX_GEOCODER_API_KEY', ''),
        'YANDEX_JAVASCRIPT_API_KEY': getattr(settings, 'YANDEX_JAVASCRIPT_API_KEY', ''),
    })


# ── Helpers ─────────────────────────────────────────────────────────


def _build_cart_items(cart):
    """Build cart_items list with products for template rendering.

    Returns:
        (cart_items, total) tuple.
    """
    total = 0
    cart_items = []
    brewing_labels = dict(Product.BREWING_CHOICES)

    for key, value in cart.items():
        try:
            product = Product.objects.get(pk=value['product_id'])
            total += float(value.get('price', 0))
            item = dict(value)
            if 'weight' in item:
                item['coffee_weight_grams'] = item['weight']
            if 'coffee_form' not in item:
                item['coffee_form'] = value.get('coffee_form', 'beans')
            brewing_method = value.get('brewing_method', '')
            item['brewing_method'] = brewing_method
            if brewing_method and brewing_method in brewing_labels:
                item['brewing_method_label'] = brewing_labels[brewing_method]
            else:
                item['brewing_method_label'] = ''
            item['product'] = product
            item['price'] = float(value.get('price', 0))
            cart_items.append(item)
        except Product.DoesNotExist:
            pass

    return cart_items, total


def _create_delivery_for_paid_order(order):
    """Create/accept Yandex delivery for a paid order.

    Called from payment_webhook and payment_result.
    Delegates to DeliveryCreator static methods.
    """
    if (
        order.delivery_method != Order.DeliveryMethod.DELIVERY
        or (
            not order.express_claim_id
            and order.yandex_order_id
        )
    ):
        return

    if order.express_claim_id:
        # Express API — accept existing claim
        DeliveryCreator.accept_express_claim_for_paid(order)
    elif not order.yandex_order_id:
        # Other Day API — create new order
        DeliveryCreator.create_other_day_for_paid(order)



