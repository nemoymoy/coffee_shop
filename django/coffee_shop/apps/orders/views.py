"""Orders views."""
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from django.db import transaction
from django.http import JsonResponse
from django.apps import apps
from django.utils import timezone

from coffee_shop.apps.catalog.models import Product
from coffee_shop.apps.catalog.services import CoffeeService, coffee_price
from coffee_shop.apps.orders.services.stock_service import StockService


def cart_view(request):
    """Отображение корзины."""
    cart = request.session.get('cart', {})
    cart_items = []
    total = 0
    
    for key, value in cart.items():
        try:
            product = Product.objects.get(pk=value['product_id'])
            price = value.get('price', 0)
            total += price
            cart_items.append({
                'product': product,
                'quantity': value.get('quantity', 1),
                'price': price,
                'coffee_weight_grams': value.get('weight'),
                'coffee_form': value.get('coffee_form'),
                'brewing_method': value.get('brewing_method'),
            })
        except Product.DoesNotExist:
            pass
    
    context = {
        'cart_items': cart_items,
        'total': total,
    }
    return render(request, 'cart.html', context)


def cart_add(request):
    """Добавление товара в корзину (AJAX)."""
    if request.method != 'POST':
        return JsonResponse({'error': 'POST required'}, status=400)
    
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
    
    Order = apps.get_model('orders', 'Order')
    OrderItem = apps.get_model('orders', 'OrderItem')
    
    if request.method == 'POST':
        first_name = request.POST.get('first_name')
        last_name = request.POST.get('last_name')
        phone = request.POST.get('phone')
        email = request.POST.get('email')
        comment = request.POST.get('comment')
        delivery_method = request.POST.get('delivery_method')
        payment_method = request.POST.get('payment_method')
        delivery_address = request.POST.get('delivery_address')
        
        # Создаём заказ
        with transaction.atomic():
            order = Order.objects.create(
                user=request.user if request.user.is_authenticated else None,
                first_name=first_name,
                last_name=last_name,
                phone=phone,
                email=email,
                comment=comment,
                delivery_method=delivery_method,
                payment_method=payment_method,
                delivery_address=delivery_address,
            )
            
            total = 0
            for key, value in cart.items():
                try:
                    product = Product.objects.get(pk=value['product_id'])
                    unit_price = value['price']
                    
                    # Валидация через StockService
                    if product.product_type == 'coffee':
                        weight = int(value['weight'])
                        available = StockService.get_available_stock(product)
                        if weight > available:
                            raise ValueError(f'На складе только {available} г')
                    else:
                        available = StockService.get_available_stock(product)
                        if available < 1:
                            raise ValueError('Товар закончился')
                    
                    OrderItem.objects.create(
                        order=order,
                        product=product,
                        quantity=1,
                        unit_price=unit_price,
                        coffee_weight_grams=value.get('weight'),
                        coffee_form=value.get('coffee_form'),
                        brewing_method=value.get('brewing_method'),
                    )
                    
                    total += unit_price
                except Product.DoesNotExist:
                    continue
            
            order.total_amount = total
            order.save()
        
        # Резервируем stock
        StockService.reserve_stock(order.pk)
        
        # Очищаем корзину
        if 'cart' in request.session:
            del request.session['cart']
        
        return redirect('orders:order_success', order_id=order.pk)
    
    context = {
        'cart_items': list(cart.values()),
    }
    return render(request, 'checkout.html', context)


def order_success(request, order_id):
    """Страница успешного заказа."""
    Order = apps.get_model('orders', 'Order')
    order = get_object_or_404(Order, pk=order_id)
    context = {'order': order}
    return render(request, 'order_success.html', context)



def payment_webhook(request):
    """Webhook endpoint for YooKassa payment notifications."""
    import json
    from django.http import JsonResponse
    from django.views.decorators.csrf import csrf_exempt
    from django.views.decorators.http import require_POST

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    signature = request.META.get('HTTP_X_YOOMONEY_SIGNATURE', '')

    from .services.yookassa_service import YooKassaService
    yookassa = YooKassaService()

    if not yookassa.verify_webhook(data, signature):
        return JsonResponse({"error": "Invalid signature"}, status=401)

    result = yookassa.process_webhook(data)

    if result.get('status') == 'paid':
        from .models import Order
        from django.db import transaction
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
