"""Celery tasks for Coffee Shop."""
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.conf import settings
from django.utils import timezone

from celery import shared_task
from celery.schedules import crontab

from coffee_shop.apps.orders.models import Order, PromoCode, OrderItem


@shared_task
def send_order_confirmation_email(order_id):
    """Отправка email подтверждения заказа."""
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return

    subject = f'Подтверждение заказа #{order_id}'
    from_email = settings.EMAIL_FROM or 'noreply@coffeeshop.local'
    recipient_list = [order.email]

    html_message = render_to_string(
        'emails/order_confirmation.html', {'order': order}
    )
    plain_message = (
        f'Заказ #{order_id} успешно оформлен. '
        f'Сумма: {order.total_amount} ₽'
    )

    send_mail(
        subject=subject,
        message=plain_message,
        from_email=from_email,
        recipient_list=recipient_list,
        html_message=html_message,
    )
    return f'Email отправлен на {order.email}'


@shared_task
def send_order_status_changed_email(order_id, new_status):
    """Отправка уведомления об изменении статуса заказа."""
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return

    status_messages = {
        'new': 'Ваш заказ принят в обработку',
        'in_progress': 'Ваш заказ в обработке',
        'ready': 'Ваш заказ готов к выдаче',
        'delivered': 'Ваш заказ доставлен',
        'cancelled': 'Ваш заказ отменён',
    }

    subject = f'Статус заказа #{order_id} обновлён'
    from_email = settings.EMAIL_FROM or 'noreply@coffeeshop.local'
    recipient_list = [order.email]

    message = status_messages.get(new_status, 'Статус заказа обновлён')

    send_mail(
        subject=subject,
        message=message,
        from_email=from_email,
        recipient_list=recipient_list,
    )
    return f'Email статуса отправлен на {order.email}'


# ------------------------------------------------------------------
# Yandex Delivery sync tasks
# ------------------------------------------------------------------

# Express API statuses that mean delivered
EXPRESS_DELIVERED_STATUSES = {
    'delivered',
    'delivered_to_address',
    'delivered_to_point',
    'delivered_finish',
}

# Other Day API statuses that mean delivered
OTHER_DAY_DELIVERED_STATUSES = {
    'delivered_to_address',
    'delivered_to_point',
    'finished',
}

# Express API statuses that mean in progress
EXPRESS_IN_PROGRESS_STATUSES = {
    'accepted',
    'performer_lookup',
    'performer_found',
    'pickup_arrived',
    'pickuped',
    'delivery_arrived',
}

# Other Day API statuses that mean in progress
OTHER_DAY_IN_PROGRESS_STATUSES = {
    'created',
    'in_work',
    'picked_up',
    'delivered',
}


def _map_yandex_status_to_order(yandex_status, api_type='express'):
    """Map Yandex Delivery status to Order status.

    Args:
        yandex_status: Status from Yandex API
        api_type: 'express' or 'other_day'

    Returns:
        Tuple (order_status, is_final)
    """
    if api_type == 'express':
        if yandex_status in EXPRESS_DELIVERED_STATUSES:
            return ('delivered', True)
        elif yandex_status in EXPRESS_IN_PROGRESS_STATUSES:
            return ('in_progress', False)
        elif yandex_status in ('new', 'estimating', 'ready_for_approval'):
            return (None, False)  # Don't update order status yet
        elif yandex_status in ('cancelled', 'rejected', 'rejection'):
            return ('canceled', True)
    else:
        # Other Day
        if yandex_status in OTHER_DAY_DELIVERED_STATUSES:
            return ('delivered', True)
        elif yandex_status in OTHER_DAY_IN_PROGRESS_STATUSES:
            return ('in_progress', False)
        elif yandex_status in ('cancelled', 'rejected', 'rejection'):
            return ('canceled', True)

    return (None, False)


@shared_task
def sync_yandex_delivery_status():
    """Periodic sync of Yandex Delivery statuses (Both Express + Other Day).

    Runs every 5 minutes.
    """
    from coffee_shop.apps.orders.services.delivery_service import (
        YandexDeliveryService,
    )

    synced = 0

    # Sync Express API claims
    express_orders = Order.objects.filter(
        delivery_method='delivery',
        delivery_api_type='express',
        status__in=['in_progress', 'ready'],
        express_claim_id__isnull=False,
    )

    service = YandexDeliveryService()
    for order in express_orders:
        result = service.get_express_claim_info(order.express_claim_id or '')

        if not result.get('success'):
            continue

        yandex_status = result.get('status', '')
        order.delivery_status = yandex_status
        order_status, is_final = _map_yandex_status_to_order(
            yandex_status, api_type='express'
        )

        if order_status:
            order.status = order_status

        order.save(update_fields=['delivery_status', 'status'])
        synced += 1

    # Sync Other Day API requests
    other_day_orders = Order.objects.filter(
        delivery_method='delivery',
        delivery_api_type='other_day',
        status__in=['in_progress', 'ready'],
        yandex_order_id__isnull=False,
    )

    for order in other_day_orders:
        result = service.get_request_info(order.yandex_order_id or '')

        if not result.get('success'):
            continue

        yandex_status = result.get('status', '')
        order.delivery_status = yandex_status
        order_status, is_final = _map_yandex_status_to_order(
            yandex_status, api_type='other_day'
        )

        if order_status:
            order.status = order_status

        order.save(update_fields=['delivery_status', 'status'])
        synced += 1

    return f'Synced {synced} of ' \
           f'{express_orders.count() + other_day_orders.count()} ' \
           f'Yandex delivery orders'


@shared_task
def accept_express_claims_pending():
    """Accept Express claims that are in new/estimating/ready_for_approval status.

    Must be called within 10 minutes of claim creation.
    Runs every 2 minutes via Celery Beat.
    """
    from coffee_shop.apps.orders.services.delivery_service import (
        YandexDeliveryService,
    )

    # Find orders with Express claims that haven't been accepted yet
    pending_orders = Order.objects.filter(
        delivery_method='delivery',
        delivery_api_type='express',
        status=Order.Status.NEW,
        express_claim_id__isnull=False,
        yandex_order_id__isnull=True,  # Not yet confirmed
    )

    accepted = 0
    service = YandexDeliveryService()

    for order in pending_orders:
        # Check claim status first
        result = service.get_express_claim_info(order.express_claim_id or '')

        if not result.get('success'):
            continue

        claim_status = result.get('status', '')

        # Accept only if still in pre-acceptance statuses
        if claim_status in ('new', 'estimating', 'ready_for_approval'):
            accept_result = service.accept_express_claim(order.express_claim_id)

            if accept_result.get('success'):
                order.yandex_order_id = order.express_claim_id
                order.status = Order.Status.AWAITING_PAYMENT
                order.save(update_fields=[
                    'yandex_order_id',
                    'status',
                    'delivery_status',
                ])
                accepted += 1

    return f'Accepted {accepted} pending Express claims'


@shared_task
def generate_daily_report():
    """Ежедневный отчёт: заказы, выручка, топ товары."""
    today = timezone.now().date()
    yesterday = today - timezone.timedelta(days=1)

    orders = Order.objects.filter(
        created_at__date=yesterday,
        status__in=['ready', 'delivered'],
    )

    from django.db.models import Sum
    total_revenue = orders.aggregate(sum_sum=Sum('total_amount'))['sum_sum'] or 0
    total_orders = orders.count()

    top_products = (
        OrderItem.objects
        .filter(order__created_at__date=yesterday)
        .values('product__name')
        .annotate(total_qty=Sum('quantity'))
        .order_by('-total_qty')[:5]
    )

    report = (
        f'=== Отчёт за {yesterday} ===\n'
        f'Заказов: {total_orders}\n'
        f'Выручка: {total_revenue} ₽\n'
        f'Топ товары: {list(top_products)[:3]}\n'
    )

    return report


@shared_task
def update_promo_codes_expiry():
    """Проверка истёкших промокодов. Запускается каждый час."""
    now = timezone.now()
    expired = PromoCode.objects.filter(
        is_active=True,
        valid_to__lt=now,
    )
    count = expired.count()
    expired.update(is_active=False)

    return f'Деактивировано: {count}'


@shared_task
def release_expired_reservations():
    """Освобождение истёкших резервов заказов."""
    from coffee_shop.apps.orders.services.stock_service import StockService
    return StockService.release_expired_reservations()
