# Generated migration for yandex_delivery_type field

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0006_order_yandex_access_token'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='yandex_delivery_type',
            field=models.CharField(
                blank=True,
                choices=[
                    ('courier', 'Курьер'),
                    ('pvz', 'Пункт выдачи (ПВЗ)'),
                    ('postomat', 'Постомат'),
                ],
                max_length=20,
                verbose_name='Тип Яндекс Доставки',
            ),
        ),
    ]
