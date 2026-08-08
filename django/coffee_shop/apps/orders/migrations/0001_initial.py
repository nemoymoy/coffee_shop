# orders/migrations/0001_initial.py

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Order',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('new', 'Новый'), ('in_progress', 'В обработке'), ('ready', 'Готов'), ('delivered', 'Доставлен'), ('cancelled', 'Отменён')], default='new', max_length=20, verbose_name='Статус')),
                ('total_amount', models.DecimalField(decimal_places=2, max_digits=12, verbose_name='Итого')),
                ('payment_method', models.CharField(choices=[('online', 'Онлайн'), ('cash', 'При получении')], max_length=10, verbose_name='Способ оплаты')),
                ('delivery_method', models.CharField(choices=[('pickup', 'Самовывоз'), ('delivery', 'Доставка')], max_length=10, verbose_name='Способ получения')),
                ('first_name', models.CharField(max_length=100, verbose_name='Имя')),
                ('last_name', models.CharField(max_length=100, verbose_name='Фамилия')),
                ('phone', models.CharField(max_length=20, verbose_name='Телефон')),
                ('email', models.EmailField(max_length=254, verbose_name='Email')),
                ('comment', models.TextField(blank=True, verbose_name='Комментарий')),
                ('delivery_address', models.TextField(blank=True, verbose_name='Адрес доставки')),
                ('delivery_date', models.DateTimeField(blank=True, null=True, verbose_name='Дата доставки')),
                ('delivery_time', models.TimeField(blank=True, null=True, verbose_name='Время доставки')),
                ('yandex_order_id', models.CharField(blank=True, max_length=100, null=True, verbose_name='ID заказа в Яндекс Доставке')),
                ('tracking_number', models.CharField(blank=True, max_length=100, null=True, verbose_name='Трек-номер')),
                ('delivery_status', models.CharField(blank=True, max_length=50, null=True, verbose_name='Статус доставки')),
                ('delivery_cost', models.DecimalField(decimal_places=2, default=0, max_digits=10, verbose_name='Стоимость доставки')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создан')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлён')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='orders', to=settings.AUTH_USER_MODEL, verbose_name='Пользователь')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='PromoCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code', models.CharField(max_length=50, unique=True, verbose_name='Код')),
                ('discount_type', models.CharField(choices=[('percent', 'Процент'), ('fixed', 'Фиксированная сумма')], max_length=10, verbose_name='Тип скидки')),
                ('discount_value', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Значение скидки')),
                ('max_uses', models.IntegerField(default=0, verbose_name='Лимит использований (0 = безлимит)')),
                ('used_count', models.IntegerField(default=0, verbose_name='Использовано')),
                ('valid_from', models.DateTimeField(verbose_name='Действует с')),
                ('valid_to', models.DateTimeField(verbose_name='Действует до')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активен')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создан')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлён')),
            ],
            options={
                'verbose_name': 'Промокод',
                'verbose_name_plural': 'Промокоды',
            },
        ),
        migrations.CreateModel(
            name='OrderItem',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('quantity', models.IntegerField(validators=[MinValueValidator(1)], verbose_name='Количество')),
                ('unit_price', models.DecimalField(decimal_places=2, max_digits=10, verbose_name='Цена за единицу')),
                ('coffee_weight_grams', models.IntegerField(blank=True, null=True, verbose_name='Вес кофе (г)')),
                ('coffee_form', models.CharField(blank=True, choices=[('beans', 'В зёрнах'), ('ground', 'Молотый')], max_length=10, null=True, verbose_name='Форма кофе')),
                ('brewing_method', models.CharField(blank=True, choices=[('turka', 'Турка (джезва)'), ('espresso', 'Эспрессо-машина'), ('geyser', 'Гейзер (мокка)'), ('pourover', 'Пуровер (воронка)'), ('siphon', 'Сифон (габет)'), ('aeropress', 'Аэропресс'), ('chemex', 'Кемекс'), ('french_press', 'Френч-пресс'), ('capping', 'Помол на каппинг'), ('filter_machine', 'Фильтр-машина')], max_length=20, null=True, verbose_name='Способ заваривания')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создана')),
                ('order', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='items', to='orders.order', verbose_name='Заказ')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, to='catalog.product', verbose_name='Товар')),
            ],
            options={
                'indexes': [models.Index(fields=['order', 'product'], name='orders_orderitem_order_id_abc123_idx')],
            },
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['status'], name='orders_order_status_123abc_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['user', 'status'], name='orders_order_user_id_456def_idx'),
        ),
        migrations.AddIndex(
            model_name='order',
            index=models.Index(fields=['created_at'], name='orders_order_created_789ghi_idx'),
        ),
    ]
