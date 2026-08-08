# orders/migrations/0003_add_yookassa_payment_id.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0002_add_check_constraints'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='yookassa_payment_id',
            field=models.CharField(
                blank=True,
                default='',
                max_length=100,
                verbose_name='ID платежа в ЮКассе',
            ),
            preserve_default=False,
        ),
    ]
