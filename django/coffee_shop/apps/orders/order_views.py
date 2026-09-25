"""Orders views."""
import json
import logging
from decimal import Decimal

from django.conf import settings

logger = logging.getLogger(__name__)
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST, require_GET

from coffee_shop.apps.catalog.models import Product
from coffee_shop.apps.catalog.services import CoffeeService, coffee_price
from coffee_shop.apps.orders.services.stock_service import StockService
from coffee_shop.apps.orders.services.promo_service import PromoService
from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService
from coffee_shop.apps.orders.services.geocoder_service import YandexGeocoderService
from coffee_shop.apps.users.models import UserEmailVerification

from coffee_shop.apps.orders.forms.order_form import OrderForm
from coffee_shop.apps.orders.models import Order, OrderItem, Package
from coffee_shop.tasks import send_order_confirmation_email, send_order_status_changed_email


def _get_express_claim_status(service, claim_id):
    """Get current status of an Express claim.

    Returns:
        {'success': True, 'status': '...'} or {'success': False, 'error': '...'}
    """
    try:
        return service.get_express_claim_info(claim_id)
    except Exception as e:
        logger.error('_get_express_claim_status error: %s', e)
        return {'success': False, 'error': str(e)}


def _create_express_delivery(service, order, coords_list, address, existing_claim_id=None):
    """Create Express delivery claim or use existing one.

    If existing_claim_id is provided, use it instead of creating a new claim.
    This avoids creating duplicate claims.

    Before accepting, checks claim status to avoid 409 Conflict
    (claim may already be accepted during price calculation).

    Returns:
        {'success': True, 'claim_id': '...', 'status': '...'}
    """
    # Build Express items
    total_weight_grams = 0
    total_quantity = 0
    for oi in order.items.all():
        total_weight_grams += oi.weight_grams if oi.weight_grams else 0
        total_quantity += oi.quantity

    try:
        package = Package.for_weight(total_weight_grams)
        total_weight_kg = (total_weight_grams / 1000.0) + float(package.tare_weight)
        sz = {
            'length': float(package.length),
            'width': float(package.width),
            'height': float(package.height),
        }
    except Package.DoesNotExist:
        total_weight_kg = total_weight_grams / 1000.0 if total_weight_grams > 0 else 0.1
        sz = {'length': 0.12, 'width': 0.06, 'height': 0.06}

    items = [{
        'title': order.items.first().product.name if order.items.first() else 'Product',
        'quantity': total_quantity,
        'cost_value': '0',
        'cost_currency': 'RUB',
        'pickup_point': 1,
        'droppof_point': 2,
        'size': sz,
        'weight': round(total_weight_kg, 3),
    }]

    route_points = [
        {
            'point_id': 1,
            'visit_order': 1,
            'type': 'source',
            'contact': {
                'name': 'Магазин',
                'phone': '+79000000000',
            },
            'address': {
                'fullname': service.shop_address,
                'coordinates': [service.shop_lon, service.shop_lat],
            },
        },
        {
            'point_id': 2,
            'visit_order': 2,
            'type': 'destination',
            'contact': {
                'name': order.recipient_name or 'Клиент',
                'phone': order.recipient_phone or '',
            },
            'address': {
                'fullname': address,
                'coordinates': coords_list if coords_list else [49.35, 53.21],
            },
        },
    ]

    # Use existing claim if provided (from price calculation)
    if existing_claim_id:
        logger.info('[Express] Using existing claim_id: %s', existing_claim_id)
        claim_id = existing_claim_id

        # Check if claim is already accepted to avoid 409 Conflict
        status_result = _get_express_claim_status(service, claim_id)
        if status_result.get('success'):
            current_status = status_result.get('status', '')
            version = status_result.get('raw', {}).get('version', 1)
            logger.info('[Express] Existing claim status: %s, version: %d', current_status, version)
            if current_status in ('confirmed', 'accepting', 'accepted'):
                logger.info('[Express] Claim already accepted, skipping accept step')
                return {
                    'success': True,
                    'claim_id': claim_id,
                    'status': current_status,
                }
            # Accept with correct version
            accept_result = service.accept_express_claim(claim_id, version=version)
        else:
            accept_result = service.accept_express_claim(claim_id)
    else:
        # Create new claim
        result = service.create_express_claim(
            items=items,
            route_points=route_points,
            client_requirements={'taxi_class': 'courier'},
        )

        if not result.get('success'):
            return result

        claim_id = result.get('claim_id')
        accept_result = service.accept_express_claim(claim_id)

    if accept_result.get('success'):
        return {
            'success': True,
            'claim_id': claim_id,
            'status': accept_result.get('status', 'accepted'),
        }
    else:
        return {
            'success': False,
            'error': f'Failed to accept claim: {accept_result.get("error")}',
        }


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
            # Маппинг полей сессии в поля шаблона
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
            item['price'] = price
            cart_with_products[key] = item
        except Product.DoesNotExist:
            pass

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


def cart_add(request):
    """Добавление товара в корзину (AJAX)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)

    if not request.user.is_authenticated:
        return JsonResponse({
            'error': 'login_required',
            'redirect': '/accounts/login/'
        }, status=403)

    # Проверка подтверждённого email
    try:
        if not request.user.email_verification.is_email_verified:
            return JsonResponse({
                'error': 'email_not_verified',
                'message': 'Для добавления товаров в корзину необходимо подтвердить email',
                'redirect': '/accounts/verification-pending/',
            }, status=403)
    except UserEmailVerification.DoesNotExist:
        # OAuth-пользователи — email уже подтверждён Яндексом
        from social_django.models import UserSocialAuth
        has_social_auth = UserSocialAuth.objects.filter(
            user=request.user
        ).exists()
        if not has_social_auth:
            return JsonResponse({
                'error': 'email_not_verified',
                'message': 'Для добавления товаров в корзину необходимо подтвердить email',
                'redirect': '/accounts/verification-pending/',
            }, status=403)

    product_id = request.POST.get('product_id')
    weight = request.POST.get('weight')
    coffee_form = request.POST.get('coffee_form')
    brewing_method = request.POST.get('brewing_method')
    
    try:
        product = Product.objects.get(pk=product_id)
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)
    
    # Валидация для кофе
    if product.product_type == 'coffee':
        is_valid, error = CoffeeService.validate_all(
            product, int(weight), coffee_form, brewing_method
        )
        if not is_valid:
            return JsonResponse({'error': error}, status=400)
        
        price = coffee_price(int(weight), product.price_per_50g)
    else:
        price = product.base_price
    
    # Сохраняем в сессии
    cart = request.session.get('cart', {})
    cart_key = f"{product_id}:{weight}:{coffee_form}:{brewing_method or ''}"
    cart[cart_key] = {
        'product_id': product_id,
        'weight': weight,
        'coffee_form': coffee_form,
        'brewing_method': brewing_method,
        'price': float(price),
        'quantity': 1,
    }
    request.session['cart'] = cart
    
    return JsonResponse({
        'success': True,
        'cart_count': len(cart),
    })


def checkout_view(request):
    """Оформление заказа."""
    cart = request.session.get('cart', {})
    if not cart:
        messages.error(request, 'Корзина пуста')
        return redirect('catalog:catalog')
    
    if request.method == 'POST':
        form = OrderForm(request.POST)
        # Расчёт стоимости товаров для отображения
        total = 0
        cart_items = []
        brewing_labels = dict(Product.BREWING_CHOICES)
        
        for key, value in cart.items():
            try:
                product = Product.objects.get(pk=value['product_id'])
                total += float(value.get('price', 0))
                item = dict(value)
                item['product'] = product
                item['price'] = float(value.get('price', 0))
                cart_items.append(item)
            except Product.DoesNotExist:
                pass
        
        if not form.is_valid():
            for field, errors in form.errors.items():
                for error in errors:
                    messages.error(request, f'{field}: {error}')
            return render(request, 'checkout.html', {
                'cart_items': cart_items,
                'form': form,
                'total': total,
            })
        
        cleaned = form.cleaned_data
        promo_code_str = cleaned.get('promo_code', '')

        # Normalize phone to +7XXXXXXXXXX format
        phone = cleaned.get('phone', '')
        if phone:
            # Remove all non-digit characters
            digits = ''.join(c for c in phone if c.isdigit())
            # If starts with 8, replace with 7
            if digits.startswith('8') and len(digits) == 11:
                digits = '7' + digits[1:]
            # If starts with 7, keep as is
            elif not digits.startswith('7') and len(digits) == 10:
                digits = '7' + digits
            # Add + prefix
            phone = '+' + digits
            cleaned['phone'] = phone
        
        # Валидация промокода
        applied_promo = None
        if promo_code_str:
            is_valid, promo, error = PromoService.validate_promo_code(promo_code_str)
            if not is_valid:
                messages.error(request, error)
                return render(request, 'checkout.html', {
                    'cart_items': cart_items,
                    'form': form,
                    'total': total,
                })
            applied_promo = promo
        
        # Сохраняем тип доставки и PVZ ID из формы (если передан)
        # JS виджет устанавливает значение в delivery_type (hidden field)
        delivery_type_raw = cleaned.get('delivery_type', '') or request.POST.get('delivery_type', '')
        if delivery_type_raw not in dict(Order.DeliveryType.choices):
            delivery_type_raw = 'courier'

        pvz_id = cleaned.get('pvz_id', '') or request.POST.get('pvz_id', '')
        destination_coords = cleaned.get('destination_coords', '') or request.POST.get('destination_coords', '')

        # Определяем API type: Курьер → Express, ПВЗ/Постомат → Other Day
        if delivery_type_raw in ('pickup', 'postamat'):
            delivery_api_type = 'other_day'
        else:
            delivery_api_type = 'express'

        # Интервал доставки (для Other Day)
        delivery_interval_from = cleaned.get('delivery_interval_from', None)
        delivery_interval_to = cleaned.get('delivery_interval_to', None)
        
        # Стоимость доставки (если выбрана через виджет)
        delivery_cost = cleaned.get('delivery_cost') or request.POST.get('delivery_cost', '0')
        if not delivery_cost:
            delivery_cost = '0'

        # Express claim ID (если выбран через виджет)
        express_claim_id = request.POST.get('express_claim_id', '')

        # Delivery date/time (если заказ создан через request/create)
        delivery_date_str = cleaned.get('delivery_date', '') or request.POST.get('delivery_date', '')
        delivery_time_str = cleaned.get('delivery_time', '') or request.POST.get('delivery_time', '')
        yandex_request_id = cleaned.get('yandex_request_id', '') or request.POST.get('yandex_request_id', '')

        # Валидация: для доставки адрес обязателен
        if cleaned['delivery_method'] == Order.DeliveryMethod.DELIVERY and not cleaned.get('delivery_address', ''):
            messages.error(request, 'Необходимо указать адрес доставки')
            return render(request, 'checkout.html', {
                'cart_items': cart_items,
                'form': form,
                'total': total,
            })
        
        # Определяем начальный статус заказа в зависимости от способа оплаты
        payment_method = cleaned['payment_method']
        if payment_method == Order.PaymentMethod.ONLINE:
            initial_status = Order.Status.AWAITING_PAYMENT
        else:
            initial_status = Order.Status.NEW

        with transaction.atomic():
            # Парсим delivery_date/delivery_time если есть
            delivery_interval_from_dt = None
            delivery_interval_to_dt = None
            if delivery_date_str and delivery_time_str:
                try:
                    from datetime import datetime, timedelta, timezone
                    # delivery_date_str = "15.09.2026", delivery_time_str = "10:00–14:00"
                    date_part = datetime.strptime(delivery_date_str, '%d.%m.%Y').date()
                    time_parts = delivery_time_str.split('–')
                    if time_parts:
                        time_from = datetime.strptime(time_parts[0].strip(), '%H:%M').time()
                        datetime_from = datetime.combine(date_part, time_from)
                        delivery_interval_from_dt = datetime_from

                        if len(time_parts) > 1:
                            time_to = datetime.strptime(time_parts[1].strip(), '%H:%M').time()
                            datetime_to = datetime.combine(date_part, time_to)
                            delivery_interval_to_dt = datetime_to
                except (ValueError, IndexError) as e:
                    logger.warning('Failed to parse delivery_date/time: %s', e)

            order = Order.objects.create(
                user=request.user if request.user.is_authenticated else None,
                first_name=cleaned['first_name'],
                last_name=cleaned['last_name'],
                phone=cleaned['phone'],
                email=cleaned['email'],
                comment=cleaned.get('comment', ''),
                delivery_method=cleaned['delivery_method'],
                delivery_type=delivery_type_raw,
                delivery_api_type=delivery_api_type,
                payment_method=payment_method,
                delivery_address=cleaned.get('delivery_address', ''),
                pvz_id=pvz_id or None,
                destination_coords=destination_coords or None,
                # client_order_id будет установлен после save
                client_order_id=None,
                delivery_interval_from=delivery_interval_from_dt or delivery_interval_from,
                delivery_interval_to=delivery_interval_to_dt or delivery_interval_to,
                recipient_name=f"{cleaned['last_name']} {cleaned['first_name']}",
                recipient_phone=cleaned['phone'],
                express_claim_id=express_claim_id or None,
                total_amount=0,
                status=initial_status,
            )
            # Устанавливаем client_order_id после создания заказа
            order.client_order_id = str(order.pk)
            order.save(update_fields=['client_order_id'])
            
            total = 0
            for key, value in cart.items():
                try:
                    product = Product.objects.get(pk=value['product_id'])
                    unit_price = value['price']
                    
                    # Валидация через доступный остаток
                    if product.product_type == 'coffee':
                        weight = int(value['weight'])
                        if weight > product.available_stock:
                            raise ValueError(f'На складе только {product.available_stock} г')
                    else:
                        if product.available_stock < 1:
                            raise ValueError('Товар закончился')
                    
                    # Определяем вес и тара
                    weight_grams = int(value.get('weight', 0)) if value.get('weight') else 0
                    package = None
                    if weight_grams > 0:
                        from coffee_shop.apps.orders.models import Package
                        try:
                            package = Package.for_weight(weight_grams)
                        except Package.DoesNotExist:
                            package = None

                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=1,
                        unit_price=unit_price,
                        coffee_weight_grams=value.get('weight'),
                        coffee_form=value.get('coffee_form'),
                        brewing_method=value.get('brewing_method'),
                        package=package,
                        weight_grams=weight_grams,
                    )
                    
                    total += unit_price
                except (Product.DoesNotExist, ValueError) as e:
                    # Неблокирующая ошибка — продолжим создание заказа
                    messages.warning(request, str(e))
                    continue
            
            # Применяем скидку промокода
            if applied_promo:
                total = PromoService.apply_discount(Decimal(str(total)), applied_promo)
                PromoService.record_promo_usage(applied_promo)
            
            order.total_amount = total
            order.save()

            # Устанавливаем стоимость доставки
            delivery_price = Decimal('0')
            if cleaned['delivery_method'] == Order.DeliveryMethod.DELIVERY:
                # Используем стоимость из формы (если пользователь выбрал через виджет)
                if delivery_cost and Decimal(str(delivery_cost)) > 0:
                    delivery_price = Decimal(str(delivery_cost))

                # Создаём заказ в Яндекс Доставке только для безналичной оплаты
                # Для онлайн-оплаты доставка создаётся после подтверждения платежа (в webhook)
                # Для Other Day API (PVZ/postamat) заказ создаётся в payment_webhook после оплаты
                if payment_method != Order.PaymentMethod.ONLINE and delivery_api_type == 'express':
                    try:
                        service = YandexDeliveryService()
                        if service.is_configured():
                            # Собираем items для API
                            # Сначала суммируем вес всех товаров
                            total_weight_grams = 0
                            total_quantity = 0
                            for oi in order.items.all():
                                total_weight_grams += oi.weight_grams if oi.weight_grams else 0
                                total_quantity += oi.quantity

                            # Теперь выбираем ОДНУ тару для суммарного веса
                            try:
                                package = Package.for_weight(total_weight_grams)
                                total_weight_kg = (total_weight_grams / 1000.0) + float(package.tare_weight)
                                sz = {
                                    'length': float(package.length),
                                    'width': float(package.width),
                                    'height': float(package.height),
                                }
                            except Package.DoesNotExist:
                                total_weight_kg = total_weight_grams / 1000.0 if total_weight_grams > 0 else 0.1
                                sz = {
                                    'length': 0.12,
                                    'width': 0.06,
                                    'height': 0.06,
                                }

                            api_items = [{
                                'quantity': total_quantity,
                                'weight': round(total_weight_kg, 3),
                                'size': sz,
                                'title': order.items.first().product.name if order.items.first() else 'Product',
                            }]

                            coords_list = []
                            if destination_coords:
                                coords_list = [float(c.strip()) for c in destination_coords.split(',')]
                            else:
                                coords_list = [49.35, 53.21]  # fallback

                            # Создаём доставку через нужный API
                            if delivery_api_type == 'express':
                                # Express API — создание + подтверждение заявки
                                # Используем существующий claim_id, если он есть (из расчёта цены)
                                existing_claim_id = cleaned.get('express_claim_id', '')
                                create_result = _create_express_delivery(
                                    service, order, coords_list,
                                    cleaned.get('delivery_address', ''),
                                    existing_claim_id or None
                                )
                            else:
                                # Other Day API — ПВЗ/Постмат
                                # Заказ создаётся в payment_webhook после успешной оплаты
                                # Здесь только сохраняем delivery_cost
                                logger.info('[Checkout] Other Day API: delivery will be created after payment confirmation')

                            if create_result.get('success'):
                                if delivery_api_type == 'express':
                                    # Если claim_id уже был (из расчёта), не перезаписываем
                                    if not order.express_claim_id:
                                        order.express_claim_id = create_result.get('claim_id', '')
                                    order.yandex_order_id = order.express_claim_id
                                    order.delivery_status = create_result.get('status', 'accepted')
                                    # Заявка уже подтверждена при расчёте цены, повторное подтверждение не нужно
                                    order.status = 'in_progress'
                                    messages.info(request, 'Заказ на доставку создан в Яндекс Доставке')
                                # Для Other Day API (PVZ/postamat) заказ создаётся в payment_webhook
                            else:
                                messages.warning(request, f'Не удалось создать заказ в Яндекс Доставке: {create_result.get("error", "unknown")}')
                    except Exception as e:
                        messages.warning(request, f'Не удалось создать заказ в Яндекс Доставке: {e}')

            # Добавляем стоимость доставки к итогу и сохраняем все изменения
            order.delivery_cost = delivery_price
            order.total_amount = Decimal(str(total)) + delivery_price

            fields_to_save = ['delivery_cost', 'total_amount']
            if order.yandex_order_id:
                fields_to_save.extend(['yandex_order_id', 'tracking_number', 'delivery_status', 'status'])
            if order.express_claim_id:
                fields_to_save.append('express_claim_id')
            if order.yandex_offer_id:
                fields_to_save.append('yandex_offer_id')

            order.save(update_fields=fields_to_save)

        # Резервируем stock (не для доставки и не для наличной оплаты — там своя логика)
        # Для online-оплаты статус уже AWAITING_PAYMENT, reserve_stock просто резервирует stock
        # Для наличной оплаты статус остаётся NEW, reserve_stock не вызывается
        if cleaned['delivery_method'] != Order.DeliveryMethod.DELIVERY and cleaned['payment_method'] == Order.PaymentMethod.ONLINE:
            StockService.reserve_stock(order.pk)
        
        # Очищаем корзину
        if 'cart' in request.session:
            del request.session['cart']
        
        # Отправляем email подтверждения заказа
        send_order_confirmation_email.delay(order.pk)
        
        return redirect('orders:order_success', order_id=order.pk)
    
    # Автозаполнение контактных данных из профиля пользователя
    user_data = {}
    if request.user.is_authenticated:
        user_data = {
            'first_name': request.user.first_name,
            'last_name': request.user.last_name,
            'email': request.user.email,
        }

    # Расчёт стоимости товаров и добавление product в cart_items
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

    from django.urls import reverse
    from django.conf import settings

    context = {
        'cart_items': cart_items,
        'form': OrderForm(initial=user_data),
        'user_data': user_data,
        'total': total,
        'YANDEX_GEOCODER_API_KEY': getattr(settings, 'YANDEX_GEOCODER_API_KEY', ''),
        'YANDEX_JAVASCRIPT_API_KEY': getattr(settings, 'YANDEX_JAVASCRIPT_API_KEY', ''),
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


def order_success(request, order_id):
    """Страница успешного заказа."""
    from decimal import Decimal
    
    order = get_object_or_404(Order, pk=order_id)
    # Рассчитываем стоимость товаров (без доставки)
    goods_total = sum((item.total_price for item in order.items.all()), Decimal('0'))
    context = {
        'order': order,
        'goods_total': goods_total,
    }
    return render(request, 'order_success.html', context)


def order_detail(request, pk):
    """Детальная страница заказа."""
    from decimal import Decimal
    
    order = get_object_or_404(Order, pk=pk)
    # Стоимость товаров = итог минус доставка
    goods_total = order.total_amount - order.delivery_cost
    context = {'order': order, 'goods_total': float(goods_total)}
    return render(request, 'order_detail.html', context)


def pay_order(request, order_id):
    """Перенаправление на страницу оплаты ЮКасса."""
    from coffee_shop.apps.orders.services.yookassa_service import YooKassaService
    from django.urls import reverse

    order = get_object_or_404(Order, pk=order_id)

    # Проверяем, что заказ требует оплаты
    if order.status != Order.Status.AWAITING_PAYMENT:
        messages.error(request, 'Этот заказ не требует оплаты')
        return redirect('orders:order_success', order_id=order.pk)

    # Проверяем, что способ оплаты — онлайн
    if order.payment_method != Order.PaymentMethod.ONLINE:
        messages.error(request, 'Для этого заказа не требуется онлайн-оплата')
        return redirect('orders:order_success', order_id=order.pk)

    # Проверяем, что ЮКасса настроена
    yookassa = YooKassaService()
    if not yookassa.is_configured():
        error_msg = yookassa.get_config_error()
        messages.error(request, error_msg or 'ЮКасса не настроена')
        return redirect('orders:order_success', order_id=order.pk)

    # Создаём платёж в ЮКассе
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
        # Сохраняем ID платежа в заказе
        order.payment_id = result.get('payment_id')
        order.save(update_fields=['payment_id'])
        # Перенаправляем на страницу оплаты ЮКассы
        return redirect(result['confirmation_url'])
    else:
        messages.error(request, f'Ошибка создания платежа: {result.get("error", "неизвестная ошибка")}')
        return redirect('orders:order_success', order_id=order.pk)


@csrf_exempt
@require_POST
def payment_webhook(request):
    """Webhook endpoint for YooKassa payment notifications."""
    import logging
    from .services.yookassa_service import YooKassaService
    from .services.delivery_service import YandexDeliveryService

    logger = logging.getLogger(__name__)

    try:
        body = request.body.decode('utf-8')
        data = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError):
        logger.error('Invalid JSON in webhook')
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    yookassa = YooKassaService()

    # Проверка подписи webhook
    signature = request.META.get('HTTP_X_YOOMONEY_SIGNATURE', '')
    if not yookassa.verify_webhook(body, signature):
        logger.error('Webhook signature verification failed')
        return HttpResponse("Forbidden", status=403)

    result = yookassa.process_webhook(data)
    logger.info('Webhook processed: %s', result)

    if result.get('status') == 'paid':
        order_number = result.get('order_number')
        payment_id = result.get('payment_id')
        logger.info('payment_webhook: Payment succeeded: order=%s, payment=%s', order_number, payment_id)
        logger.info('payment_webhook: webhook data: %s', json.dumps(data, ensure_ascii=False)[:500])

        if order_number:
            try:
                order = Order.objects.select_for_update().get(
                    order_number=order_number
                )

                # Проверяем сумму
                webhook_amount = Decimal(str(result.get('amount', '0')))
                if webhook_amount != order.total_amount:
                    return HttpResponse("Amount mismatch", status=400)

                with transaction.atomic():
                    order.payment_id = payment_id

                    # Если заказ ещё не передан в Яндекс Доставку (онлайн-оплата),
                    # создаём заказ в Яндекс Доставке сейчас
                    logger.info('payment_webhook: order=%s, delivery_method=%s, yandex_order_id=%s, express_claim_id=%s',
                               order.pk, order.delivery_method, order.yandex_order_id, order.express_claim_id)
                    if (
                        order.delivery_method == Order.DeliveryMethod.DELIVERY
                        and not order.yandex_order_id
                    ):
                        logger.info('payment_webhook: Creating/accepting Yandex delivery for order %s', order.pk)
                        service = YandexDeliveryService()
                        if service.is_configured():
                            # Express API — принимаем существующий claim
                            if order.express_claim_id:
                                logger.info('payment_webhook: accepting Express claim %s', order.express_claim_id)
                                # Get version from claim info
                                info = service.get_express_claim_info(order.express_claim_id)
                                version = info.get('raw', {}).get('version', 1) if info.get('success') else 1
                                accept_result = service.accept_express_claim(order.express_claim_id, version=version)
                                if accept_result.get('success'):
                                    order.yandex_order_id = order.express_claim_id
                                    order.delivery_status = accept_result.get('status', 'accepted')
                                    logger.info('payment_webhook: Express claim accepted: %s', accept_result.get('status'))
                                else:
                                    logger.error('payment_webhook: failed to accept Express claim: %s', accept_result.get('error'))
                            else:
                                # Other Day API — для онлайн-оплаты ПВЗ/Постмат
                                # Используем новую логику: offers/info → offers/create → request/info
                                other_day_items, other_day_places = (
                                    service._build_items_payload_for_other_day(
                                        order.items.all(), pvz_id=order.pvz_id
                                    )
                                )

                                result = service.create_order(
                                    items=other_day_items,
                                    places=other_day_places,
                                    client_order_id=order.pk,
                                    destination_coords=[],
                                    destination_address=order.delivery_address,
                                    delivery_type=order.delivery_type,
                                    pvz_id=order.pvz_id,
                                    recipient_name=order.recipient_name,
                                    recipient_phone=order.recipient_phone,
                                    email=order.email,
                                    delivery_cost=float(order.delivery_cost),
                                    payment_method='already_paid',
                                )

                                if result.get('success'):
                                    order.yandex_offer_id = result.get('offer_id')
                                    order.yandex_order_id = result.get('request_id')
                                    order.tracking_number = result.get(
                                        'delivery_time', ''
                                    )
                                    order.delivery_status = result.get('status', 'pending')
                                    logger.info(
                                        'payment_webhook: Other Day order created: '
                                        'request_id=%s, status=%s, method=%s',
                                        result.get('request_id'),
                                        result.get('status'),
                                        result.get('method'),
                                    )
                                else:
                                    logger.error(
                                        'payment_webhook: failed to create Other Day order '
                                        'for order %s: %s',
                                        order.pk, result.get('error')
                                    )
                                    if result.get('request_body'):
                                        logger.error(
                                            'payment_webhook: request_body that caused error: %s',
                                            json.dumps(result.get('request_body'), ensure_ascii=False)[:2000]
                                        )
                                    return HttpResponse('Delivery creation failed', status=400)

                    order.status = Order.Status.PAID
                    save_fields = [
                        'payment_id',
                        'status',
                        'updated_at',
                        'yandex_order_id',
                        'tracking_number',
                        'delivery_status',
                    ]
                    if order.express_claim_id:
                        save_fields.append('express_claim_id')
                    if order.yandex_offer_id:
                        save_fields.append('yandex_offer_id')
                    order.save(update_fields=save_fields)
                    logger.info('Order status updated to PAID: %s', order.pk)

                    # Отправляем email об изменении статуса
                    send_order_status_changed_email.delay(order.pk, 'in_progress')

            except (Order.DoesNotExist, ValueError) as e:
                logger.error('Error processing webhook: %s', e)

    return JsonResponse({"status": "ok"})


# ── API Endpoints for YooKassa Integration ──────────────────────────────

@csrf_exempt
@require_POST
def create_payment_api(request):
    """
    API endpoint for creating a YooKassa payment.
    Accepts order_number and amount, creates a payment and returns
    confirmation_url for redirect.
    """
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

    # Get or create order
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
    """
    Check payment status directly via API - fallback mechanism
    if webhook didn't arrive or front-end needs to check status.
    """
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
def create_refund(request):
    """
    Full or partial refund for a successful payment.
    """
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
    from decimal import Decimal
    from .services.yookassa_service import YooKassaService
    from .services.promo_service import PromoService
    from .services.stock_service import StockService
    from .services.delivery_service import YandexDeliveryService
    from coffee_shop.apps.orders.models import Package
    
    order_number = request.GET.get('order_number')
    
    if order_number:
        try:
            order = Order.objects.get(order_number=order_number)
            
            # Проверяем статус платежа через API ЮКассы
            if order.payment_id:
                yookassa = YooKassaService()
                payment_status = yookassa.get_payment_status(order.payment_id)
                
                if payment_status.get('success') and payment_status.get('paid'):
                    # Платёж успешен — обновляем статус заказа
                    if order.status != Order.Status.PAID:
                        with transaction.atomic():
                            order.status = Order.Status.PAID
                            order.save(update_fields=['status', 'updated_at'])
                            
                            # Создаём заказ в Яндекс Доставке для онлайн-оплаты
                            if (
                                order.delivery_method == Order.DeliveryMethod.DELIVERY
                                and not order.yandex_order_id
                            ):
                                service = YandexDeliveryService()
                                if service.is_configured():
                                    # Express API — принимаем существующий claim
                                    if order.express_claim_id:
                                        logger.info('payment_result: accepting Express claim %s', order.express_claim_id)
                                        # Get version from claim info
                                        info = service.get_express_claim_info(order.express_claim_id)
                                        version = info.get('raw', {}).get('version', 1) if info.get('success') else 1
                                        accept_result = service.accept_express_claim(order.express_claim_id, version=version)
                                        if accept_result.get('success'):
                                            order.yandex_order_id = order.express_claim_id
                                            order.delivery_status = accept_result.get('status', 'accepted')
                                            order.save(update_fields=['yandex_order_id', 'delivery_status', 'updated_at', 'express_claim_id'])
                                            messages.info(request, 'Заказ на доставку создан в Яндекс Доставке')
                                        else:
                                            messages.warning(request, f'Не удалось подтвердить заказ в Яндекс Доставке: {accept_result.get("error", "unknown")}')
                                    else:
                                        # Other Day API — для онлайн-оплаты ПВЗ/Постмат
                                        # Используем новую логику: offers/info → offers/create → request/info
                                        other_day_items, other_day_places = (
                                            service._build_items_payload_for_other_day(
                                                order.items.all(), pvz_id=order.pvz_id
                                            )
                                        )

                                        result = service.create_order(
                                            items=other_day_items,
                                            places=other_day_places,
                                            client_order_id=order.pk,
                                            destination_coords=[],
                                            destination_address=order.delivery_address,
                                            delivery_type=order.delivery_type,
                                            pvz_id=order.pvz_id,
                                            recipient_name=order.recipient_name,
                                            recipient_phone=order.recipient_phone,
                                            email=order.email,
                                            delivery_cost=float(order.delivery_cost),
                                            payment_method='already_paid',
                                        )

                                        if result.get('success'):
                                            order.yandex_offer_id = result.get('offer_id')
                                            order.yandex_order_id = result.get('request_id')
                                            order.tracking_number = result.get(
                                                'delivery_time', ''
                                            )
                                            order.delivery_status = result.get(
                                                'status', 'pending'
                                            )
                                            order.save(update_fields=[
                                                'yandex_order_id', 'tracking_number',
                                                'delivery_status', 'updated_at',
                                                'yandex_offer_id'
                                            ])
                                            messages.info(
                                                request,
                                                f'Заказ на доставку создан в Яндекс Доставке. '
                                                f'Интервал: {result.get("delivery_date", "")} '
                                                f'{result.get("delivery_time", "")}'
                                            )
                                        else:
                                            messages.warning(
                                                request,
                                                f'Не удалось создать заказ в Яндекс Доставке: '
                                                f'{result.get("error", "unknown")}'
                                            )
                            
                            # Резервируем stock
                            StockService.reserve_stock(order.pk)

                            # Отправляем email об изменении статуса
                            send_order_status_changed_email.delay(order.pk, 'in_progress')
                            
                    messages.success(request, 'Оплата прошла успешно!')
                elif payment_status.get('status') == 'pending':
                    messages.warning(request, 'Оплата обрабатывается. Статус обновится автоматически.')
                else:
                    messages.error(request, 'Оплата не прошла. Попробуйте снова.')
                    return redirect('orders:pay_order', order_id=order.pk)
            
            goods_total = sum(
                (item.total_price for item in order.items.all()),
                Decimal('0')
            )
            context = {
                'order': order,
                'goods_total': goods_total,
                'payment_processed': True,
            }
            return render(request, 'order_success.html', context)
        except Order.DoesNotExist:
            messages.error(request, 'Заказ не найден')
            return redirect('orders:order_success', order_id=1)
    
    messages.warning(request, 'Нет данных об оплате')
    return redirect('catalog:catalog')
