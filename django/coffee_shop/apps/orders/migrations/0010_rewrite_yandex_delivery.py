# Migration to rewrite Yandex Delivery integration from Merchant API to Cargo API.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0009_merchantaccount'),
    ]

    operations = [
        # 1. Create Package model
        migrations.CreateModel(
            name='Package',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('weight_range', models.CharField(choices=[('light', 'до 100 г'), ('medium', '100–500 г'), ('heavy', '500 г – 2 кг'), ('xl', '2–5 кг'), ('xxl', '5–10 кг')], max_length=20, unique=True, verbose_name='Диапазон веса')),
                ('length', models.DecimalField(decimal_places=3, max_digits=5, verbose_name='Длина (м)')),
                ('width', models.DecimalField(decimal_places=3, max_digits=5, verbose_name='Ширина (м)')),
                ('height', models.DecimalField(decimal_places=3, max_digits=5, verbose_name='Высота (м)')),
                ('tare_weight', models.DecimalField(decimal_places=3, max_digits=6, verbose_name='Вес коробки (кг)')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создан')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлён')),
            ],
            options={
                'verbose_name': 'Тара',
                'verbose_name_plural': 'Тары',
                'ordering': ['weight_range'],
            },
        ),

        # 2. Add initial Package data
        migrations.RunSQL(
            sql=[
                "INSERT INTO orders_package (weight_range, length, width, height, tare_weight, created_at, updated_at) VALUES "
                "('light', 0.120, 0.060, 0.060, 0.023, NOW(), NOW()), "
                "('medium', 0.200, 0.120, 0.120, 0.050, NOW(), NOW()), "
                "('heavy', 0.300, 0.200, 0.200, 0.080, NOW(), NOW()), "
                "('xl', 0.400, 0.300, 0.300, 0.150, NOW(), NOW()), "
                "('xxl', 0.500, 0.400, 0.400, 0.300, NOW(), NOW());",
            ],
            reverse_sql=[
                "DELETE FROM orders_package WHERE weight_range IN ('light', 'medium', 'heavy', 'xl', 'xxl');",
            ],
        ),

        # 3. Add package and weight_grams to OrderItem
        migrations.AddField(
            model_name='orderitem',
            name='package',
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                to='orders.package',
                verbose_name='Тара'
            ),
        ),
        migrations.AddField(
            model_name='orderitem',
            name='weight_grams',
            field=models.IntegerField(default=0, verbose_name='Вес содержимого (г)'),
        ),

        # 4. Link existing OrderItems to default package (medium)
        migrations.RunSQL(
            sql="UPDATE orders_orderitem SET package_id = (SELECT id FROM orders_package WHERE weight_range = 'medium') WHERE package_id IS NULL;",
            reverse_sql="UPDATE orders_orderitem SET package_id = NULL;",
        ),

        # 5. Add new fields to Order
        migrations.AddField(
            model_name='order',
            name='delivery_type',
            field=models.CharField(
                choices=[('courier', 'Курьер'), ('pickup', 'ПВЗ/Постомат')],
                default='courier',
                max_length=20,
                verbose_name='Тип доставки'
            ),
        ),
        migrations.AddField(
            model_name='order',
            name='pvz_id',
            field=models.CharField(blank=True, max_length=100, null=True, verbose_name='ID ПВЗ/постомата (Yandex)'),
        ),
        migrations.AddField(
            model_name='order',
            name='destination_coords',
            field=models.CharField(blank=True, max_length=50, null=True, verbose_name='Координаты доставки [lon,lat]'),
        ),

        # 6. Remove old fields from Order (using RenameField trick, then alter)
        # Drop yandex_access_token
        migrations.RemoveField(
            model_name='order',
            name='yandex_access_token',
        ),
        # Drop yandex_delivery_type
        migrations.RemoveField(
            model_name='order',
            name='yandex_delivery_type',
        ),
        # Drop yandex_merchant_id
        migrations.RemoveField(
            model_name='order',
            name='yandex_merchant_id',
        ),
        # Drop yandex_station_id
        migrations.RemoveField(
            model_name='order',
            name='yandex_station_id',
        ),
        # Drop yandex_station_name
        migrations.RemoveField(
            model_name='order',
            name='yandex_station_name',
        ),

        # 7. Delete MerchantAccount model
        migrations.DeleteModel(
            name='MerchantAccount',
        ),
    ]
