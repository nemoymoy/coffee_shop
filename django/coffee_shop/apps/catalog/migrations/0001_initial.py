# catalog/migrations/0001_initial.py

from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='Category',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Название')),
                ('slug', models.SlugField(max_length=200, unique=True, verbose_name='URL-адрес')),
                ('order', models.IntegerField(default=0, verbose_name='Порядок сортировки')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активна')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создана')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлена')),
                ('parent', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, related_name='children', to='catalog.category', verbose_name='Родительская категория')),
            ],
            options={
                'ordering': ['order', 'name'],
            },
        ),
        migrations.CreateModel(
            name='Product',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('name', models.CharField(max_length=200, verbose_name='Название')),
                ('slug', models.SlugField(max_length=200, unique=True, verbose_name='URL-адрес')),
                ('description', models.TextField(blank=True, verbose_name='Описание')),
                ('product_type', models.CharField(choices=[('coffee', 'Кофе'), ('other', 'Не кофе')], default='coffee', max_length=10, verbose_name='Тип товара')),
                ('price_per_50g', models.DecimalField(decimal_places=2, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Цена за 50 г')),
                ('base_price', models.DecimalField(decimal_places=2, default=0, max_digits=10, validators=[django.core.validators.MinValueValidator(0)], verbose_name='Базовая цена (для не кофе)')),
                ('stock', models.IntegerField(default=0, verbose_name='Остаток на складе (г)')),
                ('image', models.ImageField(blank=True, null=True, upload_to='products/', verbose_name='Изображение')),
                ('is_available', models.BooleanField(default=True, verbose_name='Доступен')),
                ('allow_grinding', models.BooleanField(default=False, verbose_name='Доступен помол')),
                ('available_brewing_methods', models.JSONField(blank=True, default=list, verbose_name='Доступные способы заваривания')),
                ('allergens', models.TextField(blank=True, verbose_name='Аллергены')),
                ('coffee_type', models.CharField(blank=True, max_length=100, verbose_name='Сорт (арабика/робуста/микс, пача, бурбон и т.д.)')),
                ('roast_level', models.CharField(blank=True, choices=[('light', 'Светлая'), ('medium', 'Средняя'), ('medium-dark', 'Средне-тёмная'), ('dark', 'Тёмная'), ('dark-roast', 'Очень тёмная')], max_length=20, verbose_name='Обжарка')),
                ('origin_region', models.CharField(blank=True, max_length=200, verbose_name='Регион (страна + ферма/кооператив)')),
                ('processing_method', models.CharField(blank=True, choices=[('natural', 'Натуральная (natural)'), ('washed', 'Мытая (washed)'), ('honey', 'Медовая (honey)'), ('anaerobic', 'Анаэробная (anaerobic)'), ('other', 'Другая')], max_length=50, verbose_name='Обработка')),
                ('sca_score', models.IntegerField(blank=True, null=True, validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(100)], verbose_name='Рейтинг SCA')),
                ('tasting_notes', models.TextField(blank=True, verbose_name='Характеристика (вкус/аромат/тело/кислотность)')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создана')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлена')),
                ('category', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='products', to='catalog.category', verbose_name='Категория')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.CreateModel(
            name='Review',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.IntegerField(choices=[(1, '1'), (2, '2'), (3, '3'), (4, '4'), (5, '5')], verbose_name='Рейтинг')),
                ('comment', models.TextField(blank=True, verbose_name='Комментарий')),
                ('is_approved', models.BooleanField(default=False, verbose_name='Одобрен')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создан')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлён')),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reviews', to='catalog.product', verbose_name='Товар')),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='category',
            index=models.Index(fields=['slug'], name='catalog_categor_slug_4f3e8a_idx'),
        ),
        migrations.AddIndex(
            model_name='category',
            index=models.Index(fields=['parent', 'is_active'], name='catalog_categor_parent_i_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['slug'], name='catalog_product_slug_1234ab_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['category', 'is_available'], name='catalog_product_categor_a1b2c3_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['stock'], name='catalog_product_stock_9876ef_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['roast_level'], name='catalog_product_roast_5544dd_idx'),
        ),
        migrations.AddIndex(
            model_name='product',
            index=models.Index(fields=['sca_score'], name='catalog_product_sca_33eeff_idx'),
        ),
        migrations.AddIndex(
            model_name='review',
            index=models.Index(fields=['product', 'is_approved'], name='catalog_review_product_77aabb_idx'),
        ),
    ]
