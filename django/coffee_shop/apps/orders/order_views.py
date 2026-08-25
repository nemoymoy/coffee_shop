"""Orders views."""
from decimal import Decimal

from django.conf import settings
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from coffee_shop.apps.catalog.models import Product
from coffee_shop.apps.catalog.services import CoffeeService, coffee_price
from coffee_shop.apps.orders.services.stock_service import StockService
from coffee_shop.apps.orders.services.promo_service import PromoService
from coffee_shop.apps.orders.services.delivery_service import YandexDeliveryService

from coffee_shop.apps.orders.forms.order_form import OrderForm
from coffee_shop.apps.orders.models import Order, OrderItem


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
        delivery_type_raw = cleaned.get('delivery_type', '') or request.POST.get('delivery_type', '')
        if delivery_type_raw not in dict(Order.DELIVERY_TYPE_CHOICES):
            delivery_type_raw = 'courier'

        pvz_id = cleaned.get('pvz_id', '') or request.POST.get('pvz_id', '')
        destination_coords = cleaned.get('destination_coords', '') or request.POST.get('destination_coords', '')
        
        # Стоимость доставки (если выбрана через виджет)
        delivery_cost = cleaned.get('delivery_cost', 0) or request.POST.get('delivery_cost', 0)

        # Валидация: для доставки адрес обязателен
        if cleaned['delivery_method'] == 'delivery' and not cleaned.get('delivery_address', ''):
            messages.error(request, 'Необходимо указать адрес доставки')
            return render(request, 'checkout.html', {
                'cart_items': cart_items,
                'form': form,
                'total': total,
            })
        
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user if request.user.is_authenticated else None,
                first_name=cleaned['first_name'],
                last_name=cleaned['last_name'],
                phone=cleaned['phone'],
                email=cleaned['email'],
                comment=cleaned.get('comment', ''),
                delivery_method=cleaned['delivery_method'],
                delivery_type=delivery_type_raw,
                payment_method=cleaned['payment_method'],
                delivery_address=cleaned.get('delivery_address', ''),
                pvz_id=pvz_id or None,
                destination_coords=destination_coords or None,
                total_amount=0,
            )
            
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
            if cleaned['delivery_method'] == 'delivery':
                # Используем стоимость из формы (если пользователь выбрал через виджет)
                if delivery_cost and Decimal(str(delivery_cost)) > 0:
                    delivery_price = Decimal(str(delivery_cost))
                    # Пытаемся создать заказ в Яндекс Доставке
                    try:
                        service = YandexDeliveryService()
                        if service.is_configured():
                            # Собираем items для API
                            api_items = []
                            for oi in order.items.all():
                                wt = oi.weight_grams / 1000.0 if oi.weight_grams else 0.5
                                sz = {}
                                if oi.package:
                                    sz = {
                                        'length': float(oi.package.length),
                                        'width': float(oi.package.width),
                                        'height': float(oi.package.height),
                                    }
                                else:
                                    sz = {'length': 0.20, 'width': 0.12, 'height': 0.12}
                                api_items.append({
                                    'quantity': oi.quantity,
                                    'weight': round(wt, 3),
                                    'size': sz,
                                    'title': oi.product.name if oi.product else 'Product',
                                })

                            coords_list = []
                            if destination_coords:
                                coords_list = [float(c.strip()) for c in destination_coords.split(',')]
                            else:
                                coords_list = [49.35, 53.21]  # fallback

                            create_result = service.create_order(
                                items=api_items,
                                client_order_id=order.pk,
                                destination_coords=coords_list,
                                destination_address=cleaned.get('delivery_address', ''),
                                delivery_type=order.delivery_type,
                                pvz_id=order.pvz_id,
                            )

                            if create_result.get('success'):
                                order.yandex_order_id = create_result.get('order_id', '')
                                order.tracking_number = create_result.get('tracking_number', '')
                                order.delivery_status = 'pending'
                                order.status = 'in_progress'
                                messages.info(request, 'Заказ на доставку создан в Яндекс Доставке')
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

            order.save(update_fields=fields_to_save)

        # Резервируем stock (не для доставки — там своя логика)
        if cleaned['delivery_method'] != 'delivery':
            StockService.reserve_stock(order.pk)
        
        # Очищаем корзину
        if 'cart' in request.session:
            del request.session['cart']
        
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
    order = get_object_or_404(Order, pk=pk)
    context = {'order': order}
    return render(request, 'order_detail.html', context)


@csrf_exempt
@require_POST
def payment_webhook(request):
    """Webhook endpoint for YooKassa payment notifications."""
    import json
    from django.http import JsonResponse

    from .services.yookassa_service import YooKassaService

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    signature = request.META.get('HTTP_X_YOOMONEY_SIGNATURE', '')

    yookassa = YooKassaService()

    if not yookassa.verify_webhook(data, signature):
        return JsonResponse({"error": "Invalid signature"}, status=401)

    result = yookassa.process_webhook(data)

    if result.get('status') == 'paid':
        try:
            order_id = result.get('order_id')
            payment_id = result.get('payment_id')
            if order_id:
                with transaction.atomic():
                    order = Order.objects.select_for_update().get(pk=int(order_id))
                    order.yookassa_payment_id = payment_id
                    order.status = 'in_progress'
                    order.save(update_fields=['yookassa_payment_id', 'status', 'updated_at'])
        except (Order.DoesNotExist, ValueError):
            pass  # Log error, do not return 500

    return JsonResponse({"status": "ok"})
