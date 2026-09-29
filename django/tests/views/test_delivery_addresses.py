"""Tests for delivery address API views."""
import pytest
from django.contrib.auth.models import User
from django.urls import reverse


pytestmark = pytest.mark.django_db


class TestDeliveryAddressesListAPI:
    """Тесты API для списка адресов доставки."""

    def test_unauthenticated_redirect(self, client):
        """Анонимный пользователь не имеет доступа."""
        response = client.get(reverse('users:delivery_addresses_api'))
        assert response.status_code == 302
        assert 'login' in response.url

    def test_list_empty_addresses(self, client, user):
        """Список пустой, если адресов нет."""
        client.login(username='testuser', password='testpass123')
        response = client.get(reverse('users:delivery_addresses_api'))

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['addresses'] == []

    def test_list_addresses(self, client, user):
        """Список адресов пользователя."""
        from coffee_shop.apps.users.models import DeliveryAddress

        client.login(username='testuser', password='testpass123')

        addr1 = DeliveryAddress.objects.create(
            user=user,
            label='Дом',
            full_address='Самара ул Революционная 3',
            apartment='15',
            coordinates='50.1627,53.2169',
            is_default=True,
        )
        addr2 = DeliveryAddress.objects.create(
            user=user,
            label='Офис',
            full_address='Самара ул Ленина 10',
            coordinates='50.1630,53.2170',
        )

        response = client.get(reverse('users:delivery_addresses_api'))

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert len(data['addresses']) == 2

        # Первый адрес должен быть дефолтным
        assert data['addresses'][0]['is_default'] is True
        assert data['addresses'][0]['label'] == 'Дом'

    def test_cannot_see_other_users_addresses(self, client, user):
        """Пользователь не видит адреса другого пользователя."""
        from coffee_shop.apps.users.models import DeliveryAddress

        other_user = User.objects.create_user(
            username='otheruser',
            password='otherpass123',
            first_name='Петр',
        )
        DeliveryAddress.objects.create(
            user=other_user,
            label='Чужой адрес',
            full_address='Чужая ул 1',
        )

        client.login(username='testuser', password='testpass123')
        response = client.get(reverse('users:delivery_addresses_api'))

        data = response.json()
        assert len(data['addresses']) == 0


class TestDeliveryAddressesCreateAPI:
    """Тесты API для создания адреса."""

    def test_unauthenticated_post(self, client):
        """Анонимный пользователь не может создавать."""
        response = client.post(reverse('users:delivery_addresses_api'),
                               content_type='application/json',
                               data='{"label": "Дом", "full_address": "Тест"}')
        assert response.status_code == 302

    def test_create_address_success(self, client, user):
        """Создание адреса."""
        client.login(username='testuser', password='testpass123')
        response = client.post(
            reverse('users:delivery_addresses_api'),
            content_type='application/json',
            data={
                'label': 'Дом',
                'full_address': 'Самара ул Революционная 3',
                'coordinates': '50.1627,53.2169',
                'apartment': '15',
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['address']['label'] == 'Дом'
        assert data['address']['apartment'] == '15'
        assert data['address']['coordinates'] == '50.1627,53.2169'

        # Проверим в БД
        from coffee_shop.apps.users.models import DeliveryAddress
        addr = DeliveryAddress.objects.get(pk=data['address']['id'])
        assert addr.user == user
        assert addr.label == 'Дом'

    def test_create_address_minimal(self, client, user):
        """Создание адреса с минимальными полями."""
        client.login(username='testuser', password='testpass123')
        response = client.post(
            reverse('users:delivery_addresses_api'),
            content_type='application/json',
            data={
                'label': 'Офис',
                'full_address': 'Москва ул Ленина 1',
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data['success'] is True
        assert data['address']['label'] == 'Офис'

    def test_create_address_missing_label(self, client, user):
        """Создание без метки — ошибка."""
        client.login(username='testuser', password='testpass123')
        response = client.post(
            reverse('users:delivery_addresses_api'),
            content_type='application/json',
            data={
                'full_address': 'Самара ул Тестовая 1',
            }
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False
        assert 'метк' in data['error'].lower() or 'label' in data

    def test_create_address_missing_address(self, client, user):
        """Создание без адреса — ошибка."""
        client.login(username='testuser', password='testpass123')
        response = client.post(
            reverse('users:delivery_addresses_api'),
            content_type='application/json',
            data={
                'label': 'Дом',
            }
        )

        assert response.status_code == 400
        data = response.json()
        assert data['success'] is False

    def test_create_address_with_is_default(self, client, user):
        """Создание с флагом is_default."""
        from coffee_shop.apps.users.models import DeliveryAddress

        client.login(username='testuser', password='testpass123')

        # Создаём первый адрес
        DeliveryAddress.objects.create(
            user=user,
            label='Офис',
            full_address='Самара ул Ленина 10',
            is_default=True,
        )

        # Создаём второй как дефолтный
        response = client.post(
            reverse('users:delivery_addresses_api'),
            content_type='application/json',
            data={
                'label': 'Дом',
                'full_address': 'Самара ул Революционная 3',
                'is_default': True,
            }
        )

        assert response.status_code == 201
        data = response.json()
        assert data['address']['is_default'] is True

        # Проверим, что первый перестал быть дефолтным
        addr1 = DeliveryAddress.objects.get(label='Офис')
        addr1.refresh_from_db()
        assert addr1.is_default is False


class TestDeliveryAddressDetailAPI:
    """Тесты API для детального управления адресом."""

    def test_get_address(self, client, user):
        """Получение адреса."""
        from coffee_shop.apps.users.models import DeliveryAddress

        addr = DeliveryAddress.objects.create(
            user=user,
            label='Дом',
            full_address='Самара ул Революционная 3',
            apartment='15',
        )

        client.login(username='testuser', password='testpass123')
        response = client.get(
            reverse('users:delivery_address_detail_api', args=[addr.pk])
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['address']['id'] == addr.pk
        assert data['address']['label'] == 'Дом'
        assert data['address']['apartment'] == '15'

    def test_get_nonexistent_address(self, client, user):
        """Получение несуществующего адреса."""
        client.login(username='testuser', password='testpass123')
        response = client.get(
            reverse('users:delivery_address_detail_api', args=[99999])
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False

    def test_get_other_users_address(self, client, user):
        """Получение чужого адреса."""
        from coffee_shop.apps.users.models import DeliveryAddress

        other_user = User.objects.create_user(
            username='otheruser',
            password='otherpass123',
        )
        addr = DeliveryAddress.objects.create(
            user=other_user,
            label='Чужой',
            full_address='Чужая ул 1',
        )

        client.login(username='testuser', password='testpass123')
        response = client.get(
            reverse('users:delivery_address_detail_api', args=[addr.pk])
        )

        assert response.status_code == 404

    def test_update_address(self, client, user):
        """Обновление адреса."""
        from coffee_shop.apps.users.models import DeliveryAddress

        addr = DeliveryAddress.objects.create(
            user=user,
            label='Дом',
            full_address='Самара ул Революционная 3',
            apartment='15',
        )

        client.login(username='testuser', password='testpass123')
        response = client.patch(
            reverse('users:delivery_address_detail_api', args=[addr.pk]),
            content_type='application/json',
            data={
                'label': 'Дом (новый)',
                'apartment': '42',
            }
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert data['address']['label'] == 'Дом (новый)'
        assert data['address']['apartment'] == '42'

        addr.refresh_from_db()
        assert addr.label == 'Дом (новый)'
        assert addr.apartment == '42'

    def test_update_is_default(self, client, user):
        """Обновление флага is_default."""
        from coffee_shop.apps.users.models import DeliveryAddress

        addr1 = DeliveryAddress.objects.create(
            user=user,
            label='Дом',
            full_address='Самара ул Революционная 3',
            is_default=True,
        )
        addr2 = DeliveryAddress.objects.create(
            user=user,
            label='Офис',
            full_address='Самара ул Ленина 10',
        )

        client.login(username='testuser', password='testpass123')
        response = client.patch(
            reverse('users:delivery_address_detail_api', args=[addr2.pk]),
            content_type='application/json',
            data={'is_default': True}
        )

        assert response.status_code == 200
        data = response.json()
        assert data['address']['is_default'] is True

        # Проверим, что addr1 больше не дефолтный
        addr1.refresh_from_db()
        assert addr1.is_default is False


class TestDeliveryAddressDeleteAPI:
    """Тесты API для удаления адресов."""

    def test_delete_address(self, client, user):
        """Удаление адреса."""
        from coffee_shop.apps.users.models import DeliveryAddress

        addr = DeliveryAddress.objects.create(
            user=user,
            label='Дом',
            full_address='Самара ул Революционная 3',
        )

        client.login(username='testuser', password='testpass123')
        response = client.post(
            reverse('users:delivery_address_delete_api', args=[addr.pk])
        )

        assert response.status_code == 200
        data = response.json()
        assert data['success'] is True
        assert not DeliveryAddress.objects.filter(pk=addr.pk).exists()

    def test_delete_nonexistent_address(self, client, user):
        """Удаление несуществующего адреса."""
        client.login(username='testuser', password='testpass123')
        response = client.post(
            reverse('users:delivery_address_delete_api', args=[99999])
        )

        assert response.status_code == 404
        data = response.json()
        assert data['success'] is False

    def test_delete_other_users_address(self, client, user):
        """Удаление чужого адреса."""
        from coffee_shop.apps.users.models import DeliveryAddress

        other_user = User.objects.create_user(
            username='otheruser',
            password='otherpass123',
        )
        addr = DeliveryAddress.objects.create(
            user=other_user,
            label='Чужой',
            full_address='Чужая ул 1',
        )

        client.login(username='testuser', password='testpass123')
        response = client.post(
            reverse('users:delivery_address_delete_api', args=[addr.pk])
        )

        assert response.status_code == 404
        assert DeliveryAddress.objects.filter(pk=addr.pk).exists()
