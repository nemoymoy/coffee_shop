# orders/migrations/0004_add_awaiting_payment_status_and_reserved_at.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0003_add_yookassa_payment_id'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='order',
            options={'ordering': ['-created_at']},
        ),
        migrations.AddField(
            model_name='order',
            name='reserved_at',
            field=models.DateTimeField(
                blank=True,
                null=True,
                verbose_name='Зарезервировано'
            ),
        ),
    ]
