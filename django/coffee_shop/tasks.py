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

    html_message = render_to_string('emails/order_confirmation.html', {'order': order})
    plain_message = f'Заказ #{order_id} успешно оформлен. Сумма: {order.total_amount} ₽'

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


@shared_task
def sync_yandex_delivery_status():
    """Периодическая синхронизация статусов Яндекс Доставки.
    Запускается каждые 5 минут.
    """
    # TODO: Реализовать при интеграции с Яндекс Доставкой
    from_orders = Order.objects.filter(
        delivery_method='delivery',
        status__in=['in_progress', 'ready'],
        yandex_order_id__isnull=False,
    )
    for order in from_orders:
        # mock: просто логируем
        pass
    return f'Проверено {from_orders.count()} заказов'


@shared_task
def generate_daily_report():
    """Ежедневный отчёт: заказы, выручка, топ товары.
    Запускается в 9:00 UTC.
    """
    today = timezone.now().date()
    yesterday = today - timezone.timedelta(days=1)

    orders = Order.objects.filter(
        created_at__date=yesterday,
        status__in=['ready', 'delivered'],
    )

    from django.db.models import Sum
    total_revenue = orders.aggregate(sum_sum=Sum('total_amount'))['sum_sum'] or 0
    total_orders = orders.count()

    # Топ товары
    from django.db.models import Sum, F
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

    # TODO: Отправка отчёта админу по email
    return report


@shared_task
def update_promo_codes_expiry():
    """Проверка истёкших промокодов.
    Запускается каждый час.
    """
    now = timezone.now()
    expired = PromoCode.objects.filter(
        is_active=True,
        valid_to__lt=now,
    )
    count = expired.count()
    expired.update(is_active=False)

    past_start = PromoCode.objects.filter(
        is_active=True,
        valid_from__gt=now,
        valid_from__lt=now + timezone.timedelta(hours=1),
    )
    # Можно деактивировать за час до старта, если нужно

    return f'Деактивировано: {count}'


@shared_task
def release_expired_reservations():
    """Освобождение истёкших резервов заказов.
    Запускается каждый час через Celery Beat.
    """
    from .apps.orders.services.stock_service import StockService
    return StockService.release_expired_reservations()
