"""Celery tasks for Coffee Shop."""
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import User
from django.urls import reverse
from django.utils import timezone

from celery import shared_task
from celery.schedules import crontab

from coffee_shop.apps.orders.models import Order, PromoCode, OrderItem
from coffee_shop.services.email_notification_service import (
    EmailNotificationService,
)


STATUS_META = {
    'new':         ('\U0001f4dd', 'Ваш заказ принят в обработку',  '#1565c0', '#e3f2fd'),
    'in_progress': ('\u2615', 'Ваш заказ в обработке',         '#e65100', '#fff3e0'),
    'ready':       ('\u2705', 'Ваш заказ готов к выдаче',      '#2e7d32', '#e8f5e9'),
    'delivered':   ('\U0001f69a', 'Ваш заказ доставлен',           '#00695c', '#e0f2f1'),
    'cancelled':   ('\u274c', 'Ваш заказ отменён',             '#c62828', '#ffebee'),
    'refunded':    ('\U0001f4b0', 'Возврат средств оформлен',      '#607d8b', '#eceff1'),
}


@shared_task
def send_order_confirmation_email(order_id):
    """Send order confirmation email to customer."""
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return

    service = EmailNotificationService()
    service.send(
        subject=f'Подтверждение заказа #{order_id}',
        template_name='emails/order_confirmation.html',
        context={
            'order': order,
            'STORE_PHONE': settings.STORE_PHONE,
            'STORE_EMAIL': settings.STORE_EMAIL,
        },
        recipient_list=[order.email],
    )


@shared_task
def send_order_to_store_email(order_id):
    """Send new order notification to store email."""
    try:
        order = Order.objects.prefetch_related('items').get(pk=order_id)
    except Order.DoesNotExist:
        return

    goods_total = sum(
        (item.total_price for item in order.items.all()),
        Decimal('0'),
    )

    service = EmailNotificationService()
    service.send(
        subject=f'Новый заказ #{order.order_number}',
        template_name='emails/order_to_store.html',
        context={
            'order': order,
            'goods_total': goods_total,
            'STORE_PHONE': settings.STORE_PHONE,
            'STORE_EMAIL': settings.STORE_EMAIL,
        },
        recipient_list=[settings.STORE_EMAIL],
    )


@shared_task
def send_order_status_changed_email(order_id, new_status):
    """Send order status change notification to customer."""
    try:
        order = Order.objects.get(pk=order_id)
    except Order.DoesNotExist:
        return

    icon, message, color, bg = STATUS_META.get(
        new_status, ('\u2615', 'Статус обновлён', '#616161', '#f5f5f5')
    )

    service = EmailNotificationService()
    service.send(
        subject=f'Статус заказа #{order_id} обновлён',
        template_name='emails/order_status_changed.html',
        context={
            'order': order,
            'status_color': color,
            'status_message': message,
            'status_icon': icon,
            'status_bg': bg,
            'STORE_PHONE': settings.STORE_PHONE,
            'STORE_EMAIL': settings.STORE_EMAIL,
        },
        recipient_list=[order.email],
    )


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
    'delivered',
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
}


def _map_yandex_status_to_order(yandex_status, api_type='express'):
    """Map Yandex Delivery status to Order status.

    Args:
        yandex_status: Status from Yandex API
        api_type: 'express' or 'other_day'

    Returns:
        Tuple (order_status, is_final)
    """
    # Yandex returns statuses in UPPER CASE, normalize for comparison
    yandex_status_lower = yandex_status.lower() if yandex_status else ''
    if api_type == 'express':
        if yandex_status_lower in EXPRESS_DELIVERED_STATUSES:
            return ('delivered', True)
        elif yandex_status_lower in EXPRESS_IN_PROGRESS_STATUSES:
            return ('in_progress', False)
        elif yandex_status_lower in ('new', 'estimating', 'ready_for_approval'):
            return (None, False)  # Don't update order status yet
        elif yandex_status_lower in ('cancelled', 'rejected', 'rejection'):
            return ('cancelled', True)
    else:
        # Other Day
        if yandex_status_lower in OTHER_DAY_DELIVERED_STATUSES:
            return ('delivered', True)
        elif yandex_status_lower in OTHER_DAY_IN_PROGRESS_STATUSES:
            return ('in_progress', False)
        elif yandex_status_lower in ('cancelled', 'rejected', 'rejection'):
            return ('cancelled', True)

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

    # Sync Express API claims — include ALL orders with express_claim_id
    # regardless of status, so we catch cancellations even for 'new' or
    # 'awaiting_payment' orders
    express_orders = Order.objects.filter(
        delivery_method='delivery',
        delivery_api_type='express',
        express_claim_id__isnull=False,
    )

    service = YandexDeliveryService()
    for order in express_orders:
        result = service.get_express_claim_info(order.express_claim_id or '')

        if not result.get('success'):
            continue

        yandex_status = result.get('status', '')
        # Сохраняем сырой статус из API Яндекс Доставки
        order.yandex_delivery_status = yandex_status.lower() if yandex_status else ''
        order.yandex_delivery_status_raw = yandex_status
        order.yandex_delivery_status_updated_at = timezone.now()
        order_status, is_final = _map_yandex_status_to_order(
            yandex_status, api_type='express'
        )

        # order.status — mapped статус для внутреннего использования
        if order_status:
            old_status = order.status
            order.status = order_status

            order.save(update_fields=[
                'yandex_delivery_status',
                'yandex_delivery_status_raw',
                'yandex_delivery_status_updated_at',
                'status',
            ])

            # Отправляем email, если статус изменился
            if old_status != order_status:
                send_order_status_changed_email.delay(order.pk, order_status)
        else:
            order.save(update_fields=[
                'yandex_delivery_status',
                'yandex_delivery_status_raw',
                'yandex_delivery_status_updated_at',
            ])

        synced += 1

    # Sync Other Day API requests — include ALL orders with yandex_order_id
    # regardless of status, so we catch cancellations for any status
    other_day_orders = Order.objects.filter(
        delivery_method='delivery',
        delivery_api_type='other_day',
        yandex_order_id__isnull=False,
    )

    for order in other_day_orders:
        result = service.get_request_info(order.yandex_order_id or '')

        if not result.get('success'):
            continue

        yandex_status = result.get('status', '')
        # Сохраняем сырой статус из API Яндекс Доставки
        order.yandex_delivery_status = yandex_status.lower() if yandex_status else ''
        order.yandex_delivery_status_raw = yandex_status
        order.yandex_delivery_status_updated_at = timezone.now()
        order_status, is_final = _map_yandex_status_to_order(
            yandex_status, api_type='other_day'
        )

        # order.status — mapped статус для внутреннего использования
        if order_status:
            old_status = order.status
            order.status = order_status

            order.save(update_fields=[
                'yandex_delivery_status',
                'yandex_delivery_status_raw',
                'yandex_delivery_status_updated_at',
                'status',
            ])

            # Отправляем email, если статус изменился
            if old_status != order_status:
                send_order_status_changed_email.delay(order.pk, order_status)
        else:
            order.save(update_fields=[
                'yandex_delivery_status',
                'yandex_delivery_status_raw',
                'yandex_delivery_status_updated_at',
            ])

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
                    'yandex_delivery_status',
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


# ------------------------------------------------------------------
# Email verification tasks
# ------------------------------------------------------------------

@shared_task(bind=True, max_retries=3)
def send_verification_email(self, user_id, token_uuid):
    """Send email verification token to user."""
    try:
        user = User.objects.get(pk=user_id)
    except User.DoesNotExist:
        return f'User {user_id} not found'

    from coffee_shop.apps.users.models import UserEmailVerification

    try:
        verification = UserEmailVerification.objects.get(
            user=user, token=token_uuid
        )
    except UserEmailVerification.DoesNotExist:
        return f'Verification token {token_uuid} not found for user {user_id}'

    verification_url = (
        f"{settings.SITE_URL}"
        f"{reverse('users:verify_email', args=[token_uuid])}"
    )

    service = EmailNotificationService()
    service.send(
        subject='Подтверждение email — Coffee Shop',
        template_name='users/email_verification.html',
        context={'user': user, 'verification_url': verification_url},
        recipient_list=[user.email],
    )

    return f'Email sent to {user.email}'
