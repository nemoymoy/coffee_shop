"""Migration for Express API + Other Day API fields.

Added fields:
- client_order_id: idempotency key (operator_request_id)
- delivery_interval_from/to: delivery time window
- recipient_name/phone: recipient info
- delivery_api_type: express vs other_day
- express_claim_id: Express API claim ID
- DeliveryType.POSTAMAT: new delivery type choice
"""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0012_update_yookassa_integration'),
    ]

    operations = [
        # New delivery type choice: Postamat
        migrations.AlterField(
            model_name='order',
            name='delivery_type',
            field=models.CharField(
                choices=[
                    ('courier', 'Курьер'),
                    ('pickup', 'ПВЗ'),
                    ('postamat', 'Постомат'),
                ],
                default='courier',
                max_length=20,
                verbose_name='Тип доставки',
            ),
        ),

        # Idempotency key
        migrations.AddField(
            model_name='order',
            name='client_order_id',
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                verbose_name='ID идемпотентности (operator_request_id)',
            ),
        ),

        # Delivery interval (Other Day API)
        migrations.AddField(
            model_name='order',
            name='delivery_interval_from',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Интервал доставки от',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='delivery_interval_to',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Интервал доставки до',
            ),
        ),

        # Recipient info
        migrations.AddField(
            model_name='order',
            name='recipient_name',
            field=models.CharField(
                blank=True,
                max_length=200,
                verbose_name='Имя получателя',
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='recipient_phone',
            field=models.CharField(
                blank=True,
                max_length=20,
                verbose_name='Телефон получателя',
            ),
        ),

        # Delivery API type
        migrations.AddField(
            model_name='order',
            name='delivery_api_type',
            field=models.CharField(
                choices=[
                    ('express', 'Express (день-в-день)'),
                    ('other_day', 'Other Day (выбранный интервал)'),
                ],
                default='other_day',
                max_length=20,
                verbose_name='Тип API Яндекс Доставки',
            ),
        ),

        # Express API claim ID
        migrations.AddField(
            model_name='order',
            name='express_claim_id',
            field=models.CharField(
                blank=True,
                max_length=100,
                null=True,
                verbose_name='ID заявки Express API',
            ),
        ),
    ]
