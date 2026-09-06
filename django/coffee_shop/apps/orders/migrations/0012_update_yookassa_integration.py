# Generated migration for YooKassa integration update

from django.db import migrations, models
from django.utils import timezone


def generate_order_numbers(apps, schema_editor):
    """Заполняем order_number для существующих записей."""
    Order = apps.get_model('orders', 'Order')
    orders = Order.objects.filter(order_number__isnull=True)
    for order in orders:
        order.order_number = f"ORD-{timezone.now().strftime('%Y%m%d')}-{order.pk:06d}"
    if orders:
        Order.objects.bulk_update(list(orders), ['order_number'], batch_size=1000)


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0011_remove_package_created_at_remove_package_updated_at_and_more'),
    ]

    operations = [
        # 1. Add order_number field (nullable)
        migrations.AddField(
            model_name='order',
            name='order_number',
            field=models.CharField(
                max_length=50,
                null=True,
                blank=True,
                verbose_name='Номер заказа'
            ),
        ),

        # 2. Rename yookassa_payment_id to payment_id
        migrations.RenameField(
            model_name='order',
            old_name='yookassa_payment_id',
            new_name='payment_id',
        ),

        # 3. Populate order_number BEFORE making it unique
        migrations.RunPython(generate_order_numbers, migrations.RunPython.noop),

        # 4. Update status choices (add REFUNDED)
        migrations.AlterField(
            model_name='order',
            name='status',
            field=models.CharField(
                max_length=20,
                choices=[
                    ('new', 'Новый'),
                    ('awaiting_payment', 'Ожидает оплаты'),
                    ('in_progress', 'Оплачен'),
                    ('ready', 'Готов'),
                    ('delivered', 'Доставлен'),
                    ('cancelled', 'Отменён'),
                    ('refunded', 'Возврат'),
                ],
                default='new',
                verbose_name='Статус'
            ),
        ),

        # 5. Now make order_number NOT NULL and UNIQUE (after population)
        migrations.AlterField(
            model_name='order',
            name='order_number',
            field=models.CharField(
                max_length=50,
                unique=True,
                verbose_name='Номер заказа'
            ),
        ),
    ]
