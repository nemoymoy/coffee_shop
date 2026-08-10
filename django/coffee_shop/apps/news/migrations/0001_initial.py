# Generated manual migration for news app

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('orders', '0004_add_awaiting_payment_status_and_reserved_at'),
    ]

    operations = [
        migrations.CreateModel(
            name='News',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Заголовок')),
                ('slug', models.SlugField(max_length=200, unique=True, verbose_name='URL-адрес')),
                ('content', models.TextField(verbose_name='Содержание')),
                ('image', models.ImageField(blank=True, null=True, upload_to='news/', verbose_name='Изображение')),
                ('is_published', models.BooleanField(default=True, verbose_name='Опубликовано')),
                ('published_at', models.DateTimeField(blank=True, null=True, verbose_name='Дата публикации')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создана')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлена')),
            ],
            options={
                'ordering': ['-published_at'],
                'verbose_name': 'Новость',
                'verbose_name_plural': 'Новости',
            },
        ),
        migrations.CreateModel(
            name='Promotion',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('title', models.CharField(max_length=200, verbose_name='Заголовок')),
                ('slug', models.SlugField(max_length=200, unique=True, verbose_name='URL-адрес')),
                ('description', models.TextField(verbose_name='Описание')),
                ('image', models.ImageField(blank=True, null=True, upload_to='promotions/', verbose_name='Изображение')),
                ('start_date', models.DateTimeField(verbose_name='Начало')),
                ('end_date', models.DateTimeField(verbose_name='Окончание')),
                ('is_active', models.BooleanField(default=True, verbose_name='Активна')),
                ('created_at', models.DateTimeField(auto_now_add=True, verbose_name='Создана')),
                ('updated_at', models.DateTimeField(auto_now=True, verbose_name='Обновлена')),
            ],
            options={
                'ordering': ['-start_date'],
                'verbose_name': 'Акция',
                'verbose_name_plural': 'Акции',
            },
        ),
        migrations.AddIndex(
            model_name='promotion',
            index=models.Index(
                fields=['is_active', 'start_date', 'end_date'],
                name='news_pro_is_acti_8f3c8e_indices',
            ),
        ),
        migrations.AddIndex(
            model_name='news',
            index=models.Index(
                fields=['slug'],
                name='news_news_slug_5e4f7a2a_indices',
            ),
        ),
        migrations.AddIndex(
            model_name='news',
            index=models.Index(
                fields=['is_published', 'published_at'],
                name='news_news_is_pub_e8f2a1b4_indices',
            ),
        ),
    ]
