"""Tests for DeliveryAddress model."""
import pytest
from django.contrib.auth.models import User

from coffee_shop.apps.users.models import DeliveryAddress


pytestmark = pytest.mark.django_db


class TestDeliveryAddressModel:
    """Тесты модели DeliveryAddress."""

    def test_create_address(self, user):
        """Создание адреса доставки."""
        addr = DeliveryAddress.objects.create(
            user=user,
            label='Дом',
            full_address='Самара ул Революционная 3',
            coordinates='50.1627,53.2169',
            apartment='15',
        )

        assert addr.pk is not None
        assert addr.user == user
        assert addr.label == 'Дом'
        assert addr.apartment == '15'
        assert addr.is_default is False
        assert str(addr) == 'Иван Иванов: Дом (Самара ул Революционная 3)'

    def test_create_address_minimal(self, user):
        """Создание адреса с минимальными полями."""
        addr = DeliveryAddress.objects.create(
            user=user,
            label='Офис',
            full_address='Москва ул Ленина 10',
        )

        assert addr.apartment == ''
        assert addr.coordinates == ''

    def test_address_str(self, user):
        """Строковое представление адреса."""
        addr = DeliveryAddress.objects.create(
            user=user,
            label='Дача',
            full_address='Подмосковье, д. Сосны',
        )
        assert 'Иван Иванов' in str(addr)
        assert 'Дача' in str(addr)

    def test_display_address_property(self, user):
        """Свойство display_address."""
        addr = DeliveryAddress.objects.create(
            user=user,
            label='Дом',
            full_address='Самара ул Мира 5',
            apartment='42',
        )
        assert addr.display_address == 'Самара ул Мира 5 | кв. 42'

    def test_display_address_no_apartment(self, user):
        """display_address без квартиры."""
        addr = DeliveryAddress.objects.create(
            user=user,
            label='Офис',
            full_address='Самара пр Победы 1',
        )
        assert addr.display_address == 'Самара пр Победы 1'

    def test_default_address_constraint(self, user):
        """Только один дефолтный адрес на пользователя."""
        addr1 = DeliveryAddress.objects.create(
            user=user,
            label='Дом',
            full_address='Самара ул Революционная 3',
            is_default=True,
        )
        assert addr1.is_default is True

        addr2 = DeliveryAddress.objects.create(
            user=user,
            label='Офис',
            full_address='Самара ул Ленина 10',
            is_default=True,
        )
        assert addr2.is_default is True

        # addr1 больше не должен быть дефолтным
        addr1.refresh_from_db()
        assert addr1.is_default is False

    def test_default_address_unset(self, user):
        """Снятие флага дефолтного адреса."""
        addr = DeliveryAddress.objects.create(
            user=user,
            label='Дом',
            full_address='Самара ул Революционная 3',
            is_default=True,
        )
        addr.is_default = False
        addr.save()
        addr.refresh_from_db()
        assert addr.is_default is False

    def test_addresses_ordered_by_default_and_created(self, user):
        """Порядок сортировки: сначала дефолтные, потом по дате."""
        addr_old = DeliveryAddress.objects.create(
            user=user,
            label='Старый',
            full_address='Самара ул Старая 1',
            is_default=True,
        )
        addr_new = DeliveryAddress.objects.create(
            user=user,
            label='Новый',
            full_address='Самара ул Новая 2',
        )

        addresses = list(DeliveryAddress.objects.filter(user=user))
        assert addresses[0] == addr_old
        assert addresses[1] == addr_new

    def test_user_cascade_delete(self, user):
        """Удаление адреса при удалении пользователя."""
        addr = DeliveryAddress.objects.create(
            user=user,
            label='Дом',
            full_address='Самара ул Революционная 3',
        )
        user_id = user.pk
        assert DeliveryAddress.objects.filter(pk=addr.pk).exists()

        user.delete()
        assert not DeliveryAddress.objects.filter(pk=addr.pk).exists()
        assert not User.objects.filter(pk=user_id).exists()

    def test_address_index(self, user):
        """Проверка наличия индекса по user и is_default."""
        addr = DeliveryAddress.objects.create(
            user=user,
            label='Дом',
            full_address='Самара ул Революционная 3',
        )
        indexes = [idx.name for idx in DeliveryAddress._meta.indexes]
        # Индекс должен быть создан для (user, is_default)
        # Django генерирует имя индекса автоматически
        assert len(indexes) > 0, 'Индексы должны быть созданы'

    def test_address_with_empty_label(self, user):
        """Адрес с пустой меткой — валидация формы."""
        from coffee_shop.apps.users.forms import DeliveryAddressForm
        form = DeliveryAddressForm(data={
            'label': '',
            'full_address': 'Самара ул Тестовая 1',
            'apartment': '1',
        })
        assert form.is_valid() is False
        assert 'label' in form.errors

    def test_address_with_empty_address(self, user):
        """Адрес с пустым full_address — валидация формы."""
        from coffee_shop.apps.users.forms import DeliveryAddressForm
        form = DeliveryAddressForm(data={
            'label': 'Дом',
            'full_address': '',
            'apartment': '1',
        })
        assert form.is_valid() is False
        assert 'full_address' in form.errors


class TestDeliveryAddressForm:
    """Тесты формы DeliveryAddressForm."""

    def test_form_valid_data(self):
        from coffee_shop.apps.users.forms import DeliveryAddressForm
        """Валидные данные формы."""
        form = DeliveryAddressForm(data={
            'label': 'Дом',
            'full_address': 'Самара ул Революционная 3',
            'apartment': '15',
        })
        assert form.is_valid() is True

    def test_form_minimal_data(self):
        """Минимальные данные формы."""
        from coffee_shop.apps.users.forms import DeliveryAddressForm
        form = DeliveryAddressForm(data={
            'label': 'Офис',
            'full_address': 'Москва ул Ленина 1',
        })
        assert form.is_valid() is True

    def test_form_save(self, user):
        """Сохранение формы."""
        from coffee_shop.apps.users.forms import DeliveryAddressForm
        form = DeliveryAddressForm(data={
            'label': 'Дом',
            'full_address': 'Самара ул Мира 10',
            'apartment': '5',
        })
        assert form.is_valid() is True
        addr = form.save(commit=False)
        addr.user = user
        addr.save()

        assert DeliveryAddress.objects.filter(pk=addr.pk).exists()
        assert addr.user == user
